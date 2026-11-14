"""
Авторизованные View для безопасной отдачи файлов.
Проверяют права пользователя на дерево перед отдачей файла.
"""

import mimetypes
import os

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views import View

from genealogy.models import ExportTask, Person, PersonPhoto


class SecureExportFileView(LoginRequiredMixin, View):
    """Безопасная отдача ZIP-архива экспорта."""

    def get(self, request, task_pk):
        task = get_object_or_404(ExportTask, pk=task_pk)

        if not task.tree.user_can_view(request.user):
            raise Http404("У вас нет доступа к этому файлу")

        if not task.file or not task.file.storage.exists(task.file.name):
            raise Http404("Файл не найден")

        response = FileResponse(
            task.file.open("rb"),
            content_type="application/zip",
            as_attachment=True,
            filename=os.path.basename(task.file.name),
        )
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response


class SecurePersonPhotoView(LoginRequiredMixin, View):
    """
    Безопасная отдача фотографии персоны.
    Поддерживает как основное фото (аватар), так и фото из галереи через ?photo_id=...
    """

    def get(self, request, person_pk):
        person = get_object_or_404(Person, pk=person_pk)

        if not person.tree.user_can_view(request.user):
            raise Http404("У вас нет доступа к этому файлу")

        photo_id = request.GET.get("photo_id")

        if photo_id:
            # Отдаём фото из галереи
            photo = get_object_or_404(PersonPhoto, pk=photo_id, person=person)
            file_field = photo.image
        else:
            # Отдаём основное фото (аватар)
            if not person.photo:
                raise Http404("Фотография не найдена")
            file_field = person.photo

        if not file_field.storage.exists(file_field.name):
            raise Http404("Файл не найден")

        # Определяем MIME-тип по расширению файла
        content_type, _ = mimetypes.guess_type(file_field.name)
        if not content_type:
            content_type = "image/jpeg"

        response = FileResponse(
            file_field.open("rb"),
            content_type=content_type,
            as_attachment=False,
        )
        # Кэшируем на 1 час
        response["Cache-Control"] = "private, max-age=3600"
        return response
