"""
Тесты для сервиса генерации отчеств.
"""
from django.test import TestCase

from genealogy.utils.names import generate_patronymic


class PatronymicGeneratorTest(TestCase):
    """Тесты генерации отчеств."""

    def test_russian_male_standard(self) -> None:
        """Русское мужское отчество (стандартное)."""
        self.assertEqual(generate_patronymic('Иван', 'male', 'ru'), 'Иванович')
        self.assertEqual(generate_patronymic('Сергей', 'male', 'ru'), 'Сергеевич')
        self.assertEqual(generate_patronymic('Александр', 'male', 'ru'), 'Александрович')

    def test_russian_female_standard(self) -> None:
        """Русское женское отчество (стандартное)."""
        self.assertEqual(generate_patronymic('Иван', 'female', 'ru'), 'Ивановна')
        self.assertEqual(generate_patronymic('Сергей', 'female', 'ru'), 'Сергеевна')

    def test_russian_male_with_y(self) -> None:
        """Русское мужское отчество от имени на -й."""
        self.assertEqual(generate_patronymic('Николай', 'male', 'ru'), 'Николаевич')
        self.assertEqual(generate_patronymic('Дмитрий', 'male', 'ru'), 'Дмитриевич')

    def test_russian_female_with_y(self) -> None:
        """Русское женское отчество от имени на -й."""
        self.assertEqual(generate_patronymic('Николай', 'female', 'ru'), 'Николаевна')

    def test_russian_male_with_a(self) -> None:
        """Русское мужское отчество от имени на -а/-я."""
        self.assertEqual(generate_patronymic('Илья', 'male', 'ru'), 'Ильич')
        self.assertEqual(generate_patronymic('Никита', 'male', 'ru'), 'Никитич')
        self.assertEqual(generate_patronymic('Кузьма', 'male', 'ru'), 'Кузьмич')

    def test_russian_female_with_a(self) -> None:
        """Русское женское отчество от имени на -а/-я."""
        self.assertEqual(generate_patronymic('Илья', 'female', 'ru'), 'Ильинична')
        self.assertEqual(generate_patronymic('Никита', 'female', 'ru'), 'Никитична')

    def test_russian_exceptions(self) -> None:
        """Русские исключения (Лев, Павел, Пётр, Лука, Фома)."""
        self.assertEqual(generate_patronymic('Лев', 'male', 'ru'), 'Львович')
        self.assertEqual(generate_patronymic('Лев', 'female', 'ru'), 'Львовна')
        self.assertEqual(generate_patronymic('Павел', 'male', 'ru'), 'Павлович')
        self.assertEqual(generate_patronymic('Пётр', 'male', 'ru'), 'Петрович')
        self.assertEqual(generate_patronymic('Пётр', 'female', 'ru'), 'Петровна')
        self.assertEqual(generate_patronymic('Лука', 'male', 'ru'), 'Лукич')
        self.assertEqual(generate_patronymic('Фома', 'male', 'ru'), 'Фомич')

    def test_ukrainian_male(self) -> None:
        """Украинское мужское отчество."""
        self.assertEqual(generate_patronymic('Іван', 'male', 'uk'), 'Іванович')

    def test_polish_male(self) -> None:
        """Польское мужское отчество."""
        self.assertEqual(generate_patronymic('Adam', 'male', 'pl'), 'Adamowicz')

    def test_polish_female(self) -> None:
        """Польское женское отчество."""
        self.assertEqual(generate_patronymic('Adam', 'female', 'pl'), 'Adamówna')

    def test_kazakh_male(self) -> None:
        """Казахское мужское отчество."""
        self.assertEqual(generate_patronymic('Нурсултан', 'male', 'kk'), 'нурсултанұлы')

    def test_kazakh_female(self) -> None:
        """Казахское женское отчество."""
        self.assertEqual(generate_patronymic('Нурсултан', 'female', 'kk'), 'нурсултанқызы')

    def test_swedish_male(self) -> None:
        """Шведское мужское отчество."""
        self.assertEqual(generate_patronymic('Erik', 'male', 'sv'), 'erikson')

    def test_swedish_female(self) -> None:
        """Шведское женское отчество."""
        self.assertEqual(generate_patronymic('Erik', 'female', 'sv'), 'erikdotter')

    def test_icelandic_male(self) -> None:
        """Исландское мужское отчество."""
        self.assertEqual(generate_patronymic('Jón', 'male', 'is'), 'jónson')

    def test_icelandic_female(self) -> None:
        """Исландское женское отчество."""
        self.assertEqual(generate_patronymic('Jón', 'female', 'is'), 'jóndóttir')

    def test_empty_name_returns_none(self) -> None:
        """Пустое имя возвращает None."""
        self.assertIsNone(generate_patronymic('', 'male', 'ru'))
        self.assertIsNone(generate_patronymic(None, 'male', 'ru'))

    def test_unknown_culture_defaults_to_russian(self) -> None:
        """Неизвестная культура использует русскую логику."""
        self.assertEqual(generate_patronymic('Иван', 'male', 'unknown'), 'Иванович')

    def test_default_culture_is_russian(self) -> None:
        """По умолчанию культура — русская."""
        self.assertEqual(generate_patronymic('Иван', 'male'), 'Иванович')

    def test_case_insensitive(self) -> None:
        """Регистронезависимая обработка."""
        self.assertEqual(generate_patronymic('иван', 'male', 'ru'), 'Иванович')
        self.assertEqual(generate_patronymic('ИВАН', 'male', 'ru'), 'Иванович')