"""
View для импорта GEDCOM-файлов.
"""

import os
import tempfile

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from genealogy.forms.export_import_forms import GedcomImportForm
from genealogy.models import (
    CollaboratorRoleEnum,
    GenderEnum,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
    TreeCollaborator,
)
from genealogy.utils.gedcom_parser import parse_gedcom_file


class GedcomImportView(LoginRequiredMixin, View):
    """View для загрузки и импорта GEDCOM-файла."""

    template_name = "genealogy/gedcom_import.html"

    def get(self, request):
        form = GedcomImportForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = GedcomImportForm(request.POST, request.FILES)

        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        gedcom_file = form.cleaned_data["gedcom_file"]
        custom_tree_name = form.cleaned_data.get("tree_name", "").strip()

        # Проверяем расширение файла
        if not gedcom_file.name.lower().endswith((".ged", ".gedcom")):
            messages.error(request, "Пожалуйста, выберите файл в формате .ged или .gedcom")
            return render(request, self.template_name, {"form": form})

        # Сохраняем файл во временное хранилище
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ged") as tmp_file:
            for chunk in gedcom_file.chunks():
                tmp_file.write(chunk)
            tmp_path = tmp_file.name

        try:
            # Парсим GEDCOM
            parsed_data = parse_gedcom_file(tmp_path)

            if not parsed_data["persons"]:
                error_msg = "В файле не найдено ни одной персоны."
                # Показываем первые 3 ошибки парсинга, если они есть, для отладки
                if parsed_data["errors"]:
                    error_msg += f" Ошибки парсинга: {'; '.join(parsed_data['errors'][:3])}"
                messages.error(request, error_msg)
                return render(request, self.template_name, {"form": form})
            # Определяем название дерева
            tree_name = custom_tree_name
            if not tree_name:
                # Добавляем временную метку для уникальности
                from django.utils import timezone

                timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
                tree_name = f"Импорт из GEDCOM ({gedcom_file.name})_{timestamp}"

            # Проверяем, существует ли дерево с таким названием
            if Tree.objects.filter(name=tree_name).exists():
                # Если существует, добавляем номер
                counter = 1
                base_name = tree_name
                while Tree.objects.filter(name=f"{base_name}_{counter}").exists():
                    counter += 1
                tree_name = f"{base_name}_{counter}"

            # Создаём дерево
            tree = Tree.objects.create(name=tree_name, description=f"Импортировано из файла {gedcom_file.name}")

            # Назначаем текущего пользователя владельцем дерева
            TreeCollaborator.objects.create(
                tree=tree, user=request.user, role=CollaboratorRoleEnum.OWNER, can_invite=True
            )
            # Импортируем данные
            result = self._import_data(tree, parsed_data)

            messages.success(
                request,
                f'✅ Дерево "{tree.name}" успешно создано! '
                f"Импортировано: {result['persons_created']} персон, "
                f"{result['relationships_created']} связей. "
                f"Пропущено дубликатов: {result['duplicates_skipped']}.",
            )

            if result["warnings"]:
                for warning in result["warnings"][:5]:  # Показываем первые 5 предупреждений
                    messages.warning(request, warning)

            return redirect("genealogy:tree_detail", pk=tree.pk)

        except Exception as e:
            messages.error(request, f"Ошибка при импорте: {e!s}")
            return render(request, self.template_name, {"form": form})

        finally:
            # Удаляем временный файл
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @transaction.atomic
    def _import_data(self, tree: Tree, parsed_data: dict) -> dict:
        """
        Импортирует распарсенные данные в базу данных.
        Возвращает статистику импорта.
        """
        persons_created = 0
        relationships_created = 0
        duplicates_skipped = 0
        warnings = []

        # Маппинг: GEDCOM ID -> Django Person ID
        gedcom_to_person = {}

        # === 1. Создаём персон ===
        for person_data in parsed_data["persons"]:
            # Проверяем на дубликаты (по ФИО + дата рождения)
            existing = self._find_duplicate(
                tree,
                person_data["first_name"],
                person_data["last_name"],
                person_data["middle_name"],
                person_data["birth_date"],
            )

            if existing:
                gedcom_to_person[person_data["gedcom_id"]] = existing.pk
                duplicates_skipped += 1
                continue

            # Определяем пол
            gender_map = {"M": GenderEnum.MALE, "F": GenderEnum.FEMALE, "U": GenderEnum.UNKNOWN}
            gender = gender_map.get(person_data["gender"], GenderEnum.UNKNOWN)

            # Создаём персону
            person = Person.objects.create(
                tree=tree,
                first_name=person_data["first_name"],
                last_name=person_data["last_name"],
                middle_name=person_data["middle_name"],
                gender=gender,
                birth_date=person_data["birth_date"],
                is_birth_date_approx=person_data.get("birth_date_approx", False),
                birth_place=person_data["birth_place"],
                death_date=person_data["death_date"],
                is_death_date_approx=person_data.get("death_date_approx", False),
                death_place=person_data["death_place"],
                burial_place=person_data["burial_place"],
                notes=person_data["notes"],
            )

            gedcom_to_person[person_data["gedcom_id"]] = person.pk
            persons_created += 1

        # === 2. Создаём связи ===
        for family_data in parsed_data["families"]:
            husband_id = gedcom_to_person.get(family_data["husband_gedcom_id"])
            wife_id = gedcom_to_person.get(family_data["wife_gedcom_id"])

            # Связь "Супруги"
            if (
                husband_id
                and wife_id
                and not Relationship.objects.filter(
                    from_person_id=husband_id, to_person_id=wife_id, relationship_type=RelationshipTypeEnum.SPOUSE
                ).exists()
            ):
                Relationship.objects.create(
                    from_person_id=husband_id,
                    to_person_id=wife_id,
                    relationship_type=RelationshipTypeEnum.SPOUSE,
                    start_date=family_data["marriage_date"],
                )
                relationships_created += 1

            # Связи "Родитель -> Ребёнок"
            children_ids = [
                gedcom_to_person.get(cid) for cid in family_data["children_gedcom_ids"] if gedcom_to_person.get(cid)
            ]

            for child_id in children_ids:
                # Отец -> Ребёнок
                if (
                    husband_id
                    and not Relationship.objects.filter(
                        from_person_id=husband_id,
                        to_person_id=child_id,
                        relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    ).exists()
                ):
                    Relationship.objects.create(
                        from_person_id=husband_id,
                        to_person_id=child_id,
                        relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    )
                    relationships_created += 1

                # Мать -> Ребёнок
                if (
                    wife_id
                    and not Relationship.objects.filter(
                        from_person_id=wife_id,
                        to_person_id=child_id,
                        relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    ).exists()
                ):
                    Relationship.objects.create(
                        from_person_id=wife_id,
                        to_person_id=child_id,
                        relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    )
                    relationships_created += 1

            for child_id in children_ids:
                # Отец -> Ребёнок
                for child_id in children_ids:
                    # Отец -> Ребёнок (объединенный if)
                    if (
                        husband_id
                        and not Relationship.objects.filter(
                            from_person_id=husband_id,
                            to_person_id=child_id,
                            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                        ).exists()
                    ):
                        Relationship.objects.create(
                            from_person_id=husband_id,
                            to_person_id=child_id,
                            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                        )
                        relationships_created += 1

                    # Мать -> Ребёнок (объединенный if)
                    if (
                        wife_id
                        and not Relationship.objects.filter(
                            from_person_id=wife_id,
                            to_person_id=child_id,
                            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                        ).exists()
                    ):
                        Relationship.objects.create(
                            from_person_id=wife_id,
                            to_person_id=child_id,
                            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                        )
                        relationships_created += 1

        return {
            "persons_created": persons_created,
            "relationships_created": relationships_created,
            "duplicates_skipped": duplicates_skipped,
            "warnings": warnings,
        }

    def _find_duplicate(
        self, tree: Tree, first_name: str, last_name: str, middle_name: str, birth_date: str
    ) -> Person | None:
        """
        Ищет существующую персону с такими же ФИО и датой рождения.
        """
        if not (first_name and last_name):
            return None

        queryset = Person.objects.filter(tree=tree, first_name__iexact=first_name, last_name__iexact=last_name)

        if middle_name:
            queryset = queryset.filter(middle_name__iexact=middle_name)

        if birth_date:
            queryset = queryset.filter(birth_date=birth_date)

        return queryset.first()
