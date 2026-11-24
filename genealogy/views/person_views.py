"""
Views для работы с персонами.
"""

import io
import logging
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import pisa

from genealogy.forms import PersonForm
from genealogy.models import Person, PersonPhoto, Tree
from genealogy.services.person_service import (
    _get_current_spouse,
    create_child_relationship,
    create_parent_for_child_relationship,
    create_parent_relationship,
    create_spouse_relationship,
)
from genealogy.utils.audit import get_client_ip, log_action
from genealogy.utils.names import decline_lastname, generate_patronymic
from genealogy.utils.relatives import get_close_relatives, get_close_relatives_for_pdf

logger = logging.getLogger(__name__)

RELATION_LABELS = {
    "son": "сын",
    "daughter": "дочь",
    "adopted_son": "приемный сын",
    "adopted_daughter": "приемная дочь",
    "father": "отец",
    "mother": "мать",
    "spouse": "супруг(а)",
}


class PersonCreateView(LoginRequiredMixin, CreateView):
    """Создание новой персоны с поддержкой контекстных параметров."""

    model = Person
    form_class = PersonForm
    template_name = "genealogy/person_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs["tree_pk"])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления персон в это дерево")

        self.parent1_id = request.GET.get("parent1_id")
        self.relation = request.GET.get("relation")
        self.spouse_of_id = request.GET.get("spouse_of")
        self.child_id = request.GET.get("child_id")

        self.parent1 = Person.objects.filter(pk=self.parent1_id).first() if self.parent1_id else None
        self.spouse_of = Person.objects.filter(pk=self.spouse_of_id).first() if self.spouse_of_id else None
        self.child = Person.objects.filter(pk=self.child_id).first() if self.child_id else None

        self.father = None
        self.mother = None

        if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            if self.parent1.gender == "male":
                self.father = self.parent1
                self.mother = _get_current_spouse(self.parent1)
            else:
                self.mother = self.parent1
                self.father = _get_current_spouse(self.parent1)

        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()

        if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            is_biological = self.relation in ["son", "daughter"]
            is_male = self.relation in ["son", "adopted_son"]

            initial["gender"] = "male" if is_male else "female"
            initial["father"] = self.father.pk if self.father else None
            initial["mother"] = self.mother.pk if self.mother else None

            if is_biological and self.father:
                if self.father.last_name:
                    initial["last_name"] = decline_lastname(
                        self.father.last_name, "male" if is_male else "female", self.father.culture or "ru"
                    )

                if self.father.first_name:
                    culture = self.father.culture or "ru"
                    patronymic = generate_patronymic(self.father.first_name, "male" if is_male else "female", culture)
                    if patronymic:
                        initial["middle_name"] = patronymic

        elif self.spouse_of:
            if self.spouse_of.gender == "male":
                initial["gender"] = "female"
            elif self.spouse_of.gender == "female":
                initial["gender"] = "male"

        elif self.parent1 and self.relation in ["father", "mother"]:
            initial["gender"] = "male" if self.relation == "father" else "female"

        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tree"] = self.tree
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tree"] = self.tree

        if self.parent1 and self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
            relation_labels = {
                "son": "сына",
                "daughter": "дочери",
                "adopted_son": "приемного сына",
                "adopted_daughter": "приемную дочь",
            }
            context["action"] = f"Создание карточки {relation_labels[self.relation]}"
            context["parent1"] = self.parent1
            context["father"] = self.father
            context["mother"] = self.mother
            context["form_mode"] = "child"
        elif self.parent1 and self.relation in ["father", "mother"]:
            context["action"] = "Создание карточки отца" if self.relation == "father" else "Создание карточки матери"
            context["child"] = self.parent1
            context["form_mode"] = "parent_of_child"
        elif self.spouse_of:
            context["action"] = "Создание карточки супруга/супруги"
            context["spouse_of"] = self.spouse_of
            context["form_mode"] = "spouse"
        elif self.child:
            context["action"] = "Создание карточки родителя"
            context["child"] = self.child
            context["form_mode"] = "parent"
        else:
            context["action"] = "Создание"
            context["form_mode"] = "default"

        return context

    def form_valid(self, form):
        has_exact_duplicate = form.exact_duplicate is not None
        has_similar_duplicates = len(form.duplicates_found) > 0

        if (has_exact_duplicate or has_similar_duplicates) and not self.request.POST.get("force_create"):
            context = self.get_context_data(form=form)
            context["exact_duplicate"] = form.exact_duplicate
            context["duplicates_found"] = form.duplicates_found
            return self.render_to_response(context)

        response = super().form_valid(form)
        person = self.object

        # === ЛОГИРОВАНИЕ: создание персоны ===

        log_action(
            tree=self.tree,
            user=self.request.user,
            action="CREATE",
            entity_type="PERSON",
            entity_id=person.pk,
            entity_name=person.full_name_display,
            ip_address=get_client_ip(self.request),
        )

        # === Создание связей через сервисный слой ===
        if self.parent1 and self.relation in ("son", "daughter", "adopted_son", "adopted_daughter"):
            result = create_child_relationship(
                parent=self.parent1,
                child=person,
                relation_type=self.relation,
                tree=self.tree,
                user=self.request.user,
                request=self.request,
            )
            messages.success(self.request, result.message)

        elif self.spouse_of:
            result = create_spouse_relationship(
                person_a=self.spouse_of,
                person_b=person,
                marriage_date=self.request.POST.get("marriage_date"),
                marriage_place=self.request.POST.get("marriage_place"),
                tree=self.tree,
                user=self.request.user,
                request=self.request,
            )
            messages.success(self.request, result.message)

        elif self.parent1 and self.relation in ("father", "mother"):
            result = create_parent_relationship(
                child=self.parent1,
                new_parent=person,
                relation_type=self.relation,
                tree=self.tree,
                user=self.request.user,
                request=self.request,
            )
            messages.success(self.request, result.message)

        elif self.child:
            result = create_parent_for_child_relationship(
                new_parent=person,
                child=self.child,
                tree=self.tree,
                user=self.request.user,
                request=self.request,
            )
            messages.success(self.request, result.message)

        else:
            messages.success(self.request, f'Персона "{person.full_name_display}" успешно создана.')

        return response

    def get_success_url(self):
        if self.parent1:
            return reverse("genealogy:person_detail", kwargs={"pk": self.parent1.pk})
        elif self.spouse_of:
            return reverse("genealogy:person_detail", kwargs={"pk": self.spouse_of.pk})
        elif self.child:
            return reverse("genealogy:person_detail", kwargs={"pk": self.child.pk})
        return reverse("genealogy:tree_detail", kwargs={"pk": self.tree.pk})


class PersonUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование существующей персоны."""

    model = Person
    form_class = PersonForm
    template_name = "genealogy/person_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.tree = self.object.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для редактирования персон в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tree"] = self.tree
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tree"] = self.tree
        context["action"] = "Редактирование"
        context["form_mode"] = "edit"
        return context

    def form_valid(self, form):
        has_exact_duplicate = form.exact_duplicate is not None
        has_similar_duplicates = len(form.duplicates_found) > 0

        if (has_exact_duplicate or has_similar_duplicates) and not self.request.POST.get("force_create"):
            context = self.get_context_data(form=form)
            context["exact_duplicate"] = form.exact_duplicate
            context["duplicates_found"] = form.duplicates_found
            return self.render_to_response(context)

        response = super().form_valid(form)

        # === ЛОГИРОВАНИЕ: редактирование персоны ===

        log_action(
            tree=self.tree,
            user=self.request.user,
            action="UPDATE",
            entity_type="PERSON",
            entity_id=self.object.pk,
            entity_name=self.object.full_name_display,
            ip_address=get_client_ip(self.request),
        )

        messages.success(self.request, f'Персона "{self.object.full_name_display}" успешно обновлена.')
        return response

    def get_success_url(self):
        return reverse("genealogy:person_detail", kwargs={"pk": self.object.pk})


class PersonDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление персоны с подтверждением."""

    model = Person
    template_name = "genealogy/person_confirm_delete.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.tree = self.object.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для удаления персон в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tree"] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()

        # === ЛОГИРОВАНИЕ: удаление персоны ===

        log_action(
            tree=self.tree,
            user=request.user,
            action="DELETE",
            entity_type="PERSON",
            entity_id=self.object.pk,
            entity_name=self.object.full_name_display,
            ip_address=get_client_ip(request),
        )

        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Персона "{self.object.full_name_display}" успешно удалена.')
        return response

    def get_success_url(self):
        return reverse("genealogy:tree_detail", kwargs={"pk": self.tree.pk})


class PersonDetailView(LoginRequiredMixin, DetailView):
    """Карточка персоны с полной информацией."""

    model = Person
    template_name = "genealogy/person_detail.html"
    context_object_name = "person"

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        if not self.object.tree.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этой персоне")
        return self.render_to_response(self.get_context_data(object=self.object))

    def get_queryset(self):
        return Person.objects.select_related("tree").prefetch_related(
            "relationships_from", "relationships_to", "life_events", "photos"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        tree = person.tree

        # 1. ГЛАВНОЕ ФОТО
        context["primary_photo"] = person.photos.filter(is_primary=True).first() or person.photos.first()

        # 2. Базовые данные и права
        context["tree"] = tree
        context["combined_timeline"] = person.get_combined_timeline()
        context["can_edit"] = tree.user_can_edit(self.request.user)

        # 3. Роль пользователя
        collaborator = tree.collaborators.filter(user=self.request.user).first()
        context["user_role"] = (
            collaborator.get_role_display()
            if collaborator
            else ("Администратор" if self.request.user.is_superuser else "Гость")
        )

        # 4. Близкие родственники — извлечено в utils.relatives
        close_relatives, father, mother = get_close_relatives(person)
        context["close_relatives"] = close_relatives
        context["father"] = father
        context["mother"] = mother

        return context


class LinkRelativeView(LoginRequiredMixin, View):
    """Выбор существующей персоны в качестве родственника."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.tree = get_object_or_404(Tree, pk=self.kwargs["tree_pk"])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления связей в это дерево")

        self.parent1_id = request.GET.get("parent1_id")
        self.relation = request.GET.get("relation")
        self.parent1 = Person.objects.filter(pk=self.parent1_id).first() if self.parent1_id else None

        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        available_persons = Person.objects.filter(tree=self.tree)

        if self.parent1:
            available_persons = available_persons.exclude(pk=self.parent1.pk)

            if self.relation in ["son", "daughter", "adopted_son", "adopted_daughter"]:
                existing_children = self.parent1.get_children()
                available_persons = available_persons.exclude(pk__in=existing_children.values_list("pk", flat=True))
            elif self.relation in ["father", "mother"]:
                existing_parents = self.parent1.get_parents()
                available_persons = available_persons.exclude(pk__in=existing_parents.values_list("pk", flat=True))
            elif self.relation == "spouse":
                existing_spouses = [s["person"] for s in self.parent1.get_spouses()]
                available_persons = available_persons.exclude(pk__in=[s.pk for s in existing_spouses])

        context = {
            "tree": self.tree,
            "parent1": self.parent1,
            "relation": self.relation,
            "available_persons": available_persons.order_by("last_name", "first_name"),
            "action": f"Выбор {RELATION_LABELS.get(self.relation, 'родственника')}",
        }

        return render(request, "genealogy/link_relative.html", context)

    def post(self, request, *args, **kwargs):
        selected_person_id = request.POST.get("selected_person")

        if not selected_person_id:
            messages.error(request, "Не выбрана персона")
            return redirect(request.get_full_path())

        selected_person = get_object_or_404(Person, pk=selected_person_id)

        if self.relation in ("son", "daughter", "adopted_son", "adopted_daughter"):
            result = create_child_relationship(
                parent=self.parent1,
                child=selected_person,
                relation_type=self.relation,
                tree=self.tree,
                user=request.user,
                request=request,
            )
            messages.success(request, result.message)

        elif self.relation in ("father", "mother"):
            result = create_parent_relationship(
                child=self.parent1,
                new_parent=selected_person,
                relation_type=self.relation,
                tree=self.tree,
                user=request.user,
                request=request,
            )
            messages.success(request, result.message)

        elif self.relation == "spouse":
            result = create_spouse_relationship(
                person_a=self.parent1,
                person_b=selected_person,
                tree=self.tree,
                user=request.user,
                request=request,
            )
            messages.success(request, result.message)

        return redirect("genealogy:person_detail", pk=self.parent1.pk)


class PersonPhotoUploadView(LoginRequiredMixin, View):
    """Загрузка новой фотографии для персоны."""

    def post(self, request, person_pk):
        person = get_object_or_404(Person, pk=person_pk)
        if not person.tree.user_can_edit(request.user):
            messages.error(request, "У вас нет прав для добавления фотографий.")
            return redirect("genealogy:person_detail", pk=person_pk)

        image = request.FILES.get("photo")
        caption = request.POST.get("caption", "").strip()
        is_primary = request.POST.get("is_primary") == "on"

        if not image:
            messages.error(request, "Пожалуйста, выберите файл изображения.")
            return redirect("genealogy:person_detail", pk=person_pk)

        # Если это главное фото, обновляем аватар персоны
        if is_primary:
            person.photo = image
            person.save()

        # Создаём запись в галерее (ОДИН РАЗ!)
        photo = PersonPhoto.objects.create(person=person, image=image, caption=caption, is_primary=is_primary)

        # === ЛОГИРОВАНИЕ: загрузка фото ===

        log_action(
            tree=person.tree,
            user=request.user,
            action="CREATE",
            entity_type="PHOTO",
            entity_id=photo.pk,
            entity_name=f"Фото для {person.full_name_display}",
            ip_address=get_client_ip(request),
        )

        messages.success(request, "Фотография успешно добавлена.")
        return redirect("genealogy:person_detail", pk=person_pk)


class PersonPhotoDeleteView(LoginRequiredMixin, View):
    """Удаление фотографии из галереи."""

    def post(self, request, photo_pk):
        from genealogy.models import PersonPhoto

        photo = get_object_or_404(PersonPhoto, pk=photo_pk)

        if not photo.person.tree.user_can_edit(request.user):
            messages.error(request, "У вас нет прав для удаления фотографий.")
            return redirect("genealogy:person_detail", pk=photo.person.pk)

        person_pk = photo.person.pk

        # Если удаляем главное фото, очищаем аватар
        if photo.is_primary:
            photo.person.photo = None
            photo.person.save()

        # === ЛОГИРОВАНИЕ: удаление фото ===

        log_action(
            tree=photo.person.tree,
            user=request.user,
            action="DELETE",
            entity_type="PHOTO",
            entity_id=photo.pk,
            entity_name=f"Фото {photo.person.full_name_display}",
            ip_address=get_client_ip(request),
        )

        if photo.image:
            photo.image.delete(save=False)

        photo.delete()
        messages.success(request, "Фотография удалена.")
        return redirect("genealogy:person_detail", pk=person_pk)


class PersonPhotoSetPrimaryView(LoginRequiredMixin, View):
    """Установка фотографии как главной (аватар)."""

    def post(self, request, photo_pk):
        from genealogy.models import PersonPhoto

        photo = get_object_or_404(PersonPhoto, pk=photo_pk)

        if not photo.person.tree.user_can_edit(request.user):
            messages.error(request, "У вас нет прав для изменения фотографий.")
            return redirect("genealogy:person_detail", pk=photo.person.pk)

        # Сбрасываем все другие фото как неглавные
        PersonPhoto.objects.filter(person=photo.person).update(is_primary=False)

        # Устанавливаем текущее как главное
        photo.is_primary = True
        photo.save()

        # Обновляем аватар персоны
        photo.person.photo = photo.image
        photo.person.save()

        messages.success(request, "Фотография установлена как главная.")
        return redirect("genealogy:person_detail", pk=photo.person.pk)


class PersonPDFView(LoginRequiredMixin, DetailView):
    """Генерация PDF-отчёта по персоне."""

    model = Person
    template_name = "genealogy/person_pdf.html"

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.object = self.get_object()
        if not self.object.tree.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этой персоне")

        # === 1. РЕГИСТРАЦИЯ ШРИФТА ИЗ ПАПКИ ПРОЕКТА ===
        # Формируем абсолютный путь к шрифту внутри проекта
        font_path = os.path.join(settings.BASE_DIR, "genealogy", "fonts", "arial.ttf")

        try:
            # Регистрируем шрифт под именем 'ArialCyr'
            pdfmetrics.registerFont(TTFont("ArialCyr", font_path))

            # Регистрируем семейство шрифтов (требование reportlab)
            pdfmetrics.registerFontFamily(
                "ArialCyr", normal="ArialCyr", bold="ArialCyr", italic="ArialCyr", boldItalic="ArialCyr"
            )

            # 🔥 КЛЮЧЕВОЙ МОМЕНТ: Подменяем стандартные шрифты PDF на наш кириллический!
            # Это гарантирует, что даже если xhtml2pdf проигнорирует CSS font-family,
            # он всё равно будет использовать ArialCyr для рендеринга текста.
            pdfmetrics.registerFontFamily(
                "Helvetica", normal="ArialCyr", bold="ArialCyr", italic="ArialCyr", boldItalic="ArialCyr"
            )
            pdfmetrics.registerFontFamily(
                "Times-Roman", normal="ArialCyr", bold="ArialCyr", italic="ArialCyr", boldItalic="ArialCyr"
            )

            logger.info("Шрифт загружен и стандартные шрифты PDF подменены: %s", font_path)
        except Exception:
            logger.exception(
                "Не удалось загрузить шрифт. Проверьте, что файл лежит здесь: %s", font_path,
            )
        # =================================================

        # Получаем контекст
        context = self.get_context_data(object=self.object)

        from django.utils import timezone

        context["current_date"] = timezone.now()

        # Обрабатываем фото для PDF (xhtml2pdf требует абсолютный путь)
        primary_photo = context.get("primary_photo")
        if primary_photo and primary_photo.image:
            photo_path = os.path.join(settings.MEDIA_ROOT, primary_photo.image.name)
            if os.path.exists(photo_path):
                context["primary_photo_url"] = "file:///" + photo_path.replace("\\", "/")
            else:
                context["primary_photo_url"] = None
        else:
            context["primary_photo_url"] = None

        # Рендерим HTML
        from django.template.loader import render_to_string

        html_string = render_to_string(self.template_name, context, request=request)

        # Генерируем PDF

        result_buffer = io.BytesIO()
        pdf = pisa.CreatePDF(html_string, dest=result_buffer, encoding="utf-8")

        if pdf.err:
            messages.error(request, "Ошибка при генерации PDF")
            return redirect("genealogy:person_detail", pk=self.object.pk)

        # Логируем действие

        log_action(
            tree=self.object.tree,
            user=request.user,
            action="EXPORT",
            entity_type="PERSON",
            entity_id=self.object.pk,
            entity_name=f"PDF-отчёт: {self.object.full_name_display}",
            ip_address=get_client_ip(request),
        )

        # Возвращаем PDF
        from django.http import HttpResponse

        response = HttpResponse(result_buffer.getvalue(), content_type="application/pdf")

        safe_name = self.object.full_name_display.replace(" ", "_")[:50]
        for char in '<>:"/\\|?*':
            safe_name = safe_name.replace(char, "_")

        filename = f"{safe_name}_{timezone.now().strftime('%Y%m%d')}.pdf"

        from urllib.parse import quote

        ascii_filename = f"person_{self.object.pk}_{timezone.now().strftime('%Y%m%d')}.pdf"
        encoded_filename = quote(filename, safe="")

        response["Content-Disposition"] = (
            f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"
        )

        return response

    def get_queryset(self):
        return Person.objects.select_related("tree").prefetch_related(
            "relationships_from", "relationships_to", "life_events", "photos"
        )

    def get_context_data(self, **kwargs):
        # Переиспользуем логику из PersonDetailView
        context = super().get_context_data(**kwargs)
        person = self.object
        tree = person.tree

        context["primary_photo"] = person.photos.filter(is_primary=True).first() or person.photos.first()
        context["tree"] = tree
        context["combined_timeline"] = person.get_combined_timeline()
        context["can_edit"] = tree.user_can_edit(self.request.user)

        # Блок родственников — упрощённая версия для PDF (без rel_obj)
        context["close_relatives"] = get_close_relatives_for_pdf(person)
        return context
