"""
Views для экспорта и импорта данных.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView

from genealogy.forms import ExportForm, ImportForm
from genealogy.models import ExportTask, Tree
from genealogy.services.export_service import ExportService
from genealogy.services.import_service import ImportService


class TreeExportView(LoginRequiredMixin, View):
    """Страница настройки и запуска экспорта дерева."""

    template_name = "genealogy/tree_export.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.tree = get_object_or_404(Tree, pk=self.kwargs["pk"])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для экспорта этого дерева")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"form": ExportForm(tree=self.tree), "tree": self.tree})

    def post(self, request, *args, **kwargs):
        form = ExportForm(request.POST, tree=self.tree)
        if form.is_valid():
            service = ExportService()
            task = service.create_export_task(
                user=request.user,
                tree=self.tree,
                export_type=form.cleaned_data["export_type"],
                export_format=form.cleaned_data["export_format"],
                target_person=form.cleaned_data.get("target_person"),
            )
            try:
                service.execute_export(task)
                messages.success(request, "Экспорт успешно завершён. Файл готов к скачиванию.")
                return redirect("genealogy:tree_export_result", pk=self.tree.pk, task_pk=task.pk)
            except Exception as e:
                messages.error(request, f"Ошибка при экспорте: {e}")
                return redirect("genealogy:tree_detail", pk=self.tree.pk)
        return render(request, self.template_name, {"form": form, "tree": self.tree})


class TreeExportResultView(LoginRequiredMixin, DetailView):
    """Страница результата экспорта со ссылкой на скачивание."""

    model = ExportTask
    template_name = "genealogy/tree_export_result.html"
    context_object_name = "task"

    def get_queryset(self):
        return ExportTask.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tree"] = self.object.tree
        return context


class TreeImportView(LoginRequiredMixin, View):
    """Страница загрузки файла и запуска импорта."""

    template_name = "genealogy/tree_import.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"form": ImportForm(user=request.user)})

    def post(self, request, *args, **kwargs):
        form = ImportForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            service = ImportService()
            task = service.create_import_task(
                user=request.user,
                source_file=request.FILES["source_file"],
                target_tree=form.cleaned_data.get("target_tree"),
            )
            try:
                service.execute_import(task)
                messages.success(
                    request,
                    f"Импорт успешно завершён. Импортировано персон: {task.person_count}, связей: {task.relationship_count}.",
                )
                return (
                    redirect("genealogy:tree_detail", pk=task.tree.pk) if task.tree else redirect("genealogy:tree_list")
                )
            except Exception as e:
                messages.error(request, f"Ошибка при импорте: {e}")
                return redirect("genealogy:tree_import")
        return render(request, self.template_name, {"form": form})
