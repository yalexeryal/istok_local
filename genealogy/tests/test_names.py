"""
Тесты для сервиса генерации отчеств и склонения фамилий.
"""

from django.test import TestCase

from genealogy.utils.names import decline_lastname, generate_patronymic


class PatronymicGeneratorTest(TestCase):
    """Тесты генерации отчеств."""

    def test_russian_male_standard(self) -> None:
        self.assertEqual(generate_patronymic("Иван", "male", "ru"), "Иванович")
        self.assertEqual(generate_patronymic("Сергей", "male", "ru"), "Сергеевич")
        self.assertEqual(generate_patronymic("Александр", "male", "ru"), "Александрович")

    def test_russian_female_standard(self) -> None:
        self.assertEqual(generate_patronymic("Иван", "female", "ru"), "Ивановна")
        self.assertEqual(generate_patronymic("Сергей", "female", "ru"), "Сергеевна")

    def test_russian_male_with_y(self) -> None:
        self.assertEqual(generate_patronymic("Николай", "male", "ru"), "Николаевич")
        self.assertEqual(generate_patronymic("Дмитрий", "male", "ru"), "Дмитриевич")

    def test_russian_female_with_y(self) -> None:
        self.assertEqual(generate_patronymic("Николай", "female", "ru"), "Николаевна")

    def test_russian_male_with_a(self) -> None:
        self.assertEqual(generate_patronymic("Илья", "male", "ru"), "Ильич")
        self.assertEqual(generate_patronymic("Никита", "male", "ru"), "Никитич")
        self.assertEqual(generate_patronymic("Кузьма", "male", "ru"), "Кузьмич")

    def test_russian_female_with_a(self) -> None:
        self.assertEqual(generate_patronymic("Илья", "female", "ru"), "Ильинична")
        self.assertEqual(generate_patronymic("Никита", "female", "ru"), "Никитична")

    def test_russian_exceptions(self) -> None:
        self.assertEqual(generate_patronymic("Лев", "male", "ru"), "Львович")
        self.assertEqual(generate_patronymic("Лев", "female", "ru"), "Львовна")
        self.assertEqual(generate_patronymic("Павел", "male", "ru"), "Павлович")
        self.assertEqual(generate_patronymic("Пётр", "male", "ru"), "Петрович")
        self.assertEqual(generate_patronymic("Пётр", "female", "ru"), "Петровна")
        self.assertEqual(generate_patronymic("Лука", "male", "ru"), "Лукич")
        self.assertEqual(generate_patronymic("Лука", "female", "ru"), "Лукична")
        self.assertEqual(generate_patronymic("Фома", "male", "ru"), "Фомич")

    def test_ukrainian_male(self) -> None:
        self.assertEqual(generate_patronymic("Іван", "male", "uk"), "Іванович")

    def test_polish_male(self) -> None:
        self.assertEqual(generate_patronymic("Adam", "male", "pl"), "Adamowicz")

    def test_polish_female(self) -> None:
        self.assertEqual(generate_patronymic("Adam", "female", "pl"), "Adamówna")

    def test_kazakh_male(self) -> None:
        self.assertEqual(generate_patronymic("Нурсултан", "male", "kk"), "нурсултанұлы")

    def test_kazakh_female(self) -> None:
        self.assertEqual(generate_patronymic("Нурсултан", "female", "kk"), "нурсултанқызы")

    def test_swedish_male(self) -> None:
        self.assertEqual(generate_patronymic("Erik", "male", "sv"), "erikson")

    def test_swedish_female(self) -> None:
        self.assertEqual(generate_patronymic("Erik", "female", "sv"), "erikdotter")

    def test_icelandic_male(self) -> None:
        self.assertEqual(generate_patronymic("Jón", "male", "is"), "jónson")

    def test_icelandic_female(self) -> None:
        self.assertEqual(generate_patronymic("Jón", "female", "is"), "jóndóttir")

    def test_empty_name_returns_none(self) -> None:
        self.assertIsNone(generate_patronymic("", "male", "ru"))
        self.assertIsNone(generate_patronymic(None, "male", "ru"))

    def test_unknown_culture_defaults_to_russian(self) -> None:
        self.assertEqual(generate_patronymic("Иван", "male", "unknown"), "Иванович")

    def test_default_culture_is_russian(self) -> None:
        self.assertEqual(generate_patronymic("Иван", "male"), "Иванович")

    def test_case_insensitive(self) -> None:
        self.assertEqual(generate_patronymic("иван", "male", "ru"), "Иванович")
        self.assertEqual(generate_patronymic("ИВАН", "male", "ru"), "Иванович")


class LastnameDeclensionTest(TestCase):
    """Тесты склонения фамилий."""

    def test_male_lastname_unchanged(self) -> None:
        """Мужские фамилии не изменяются."""
        self.assertEqual(decline_lastname("Иванов", "male", "ru"), "Иванов")
        self.assertEqual(decline_lastname("Сергеев", "male", "ru"), "Сергеев")
        self.assertEqual(decline_lastname("Путин", "male", "ru"), "Путин")

    def test_russian_ov(self) -> None:
        """Русские фамилии на -ов."""
        self.assertEqual(decline_lastname("Иванов", "female", "ru"), "Иванова")
        self.assertEqual(decline_lastname("Сергеев", "female", "ru"), "Сергеева")
        self.assertEqual(decline_lastname("Достоевский", "female", "ru"), "Достоевская")

    def test_russian_in(self) -> None:
        """Русские фамилии на -ин."""
        self.assertEqual(decline_lastname("Путин", "female", "ru"), "Путина")

    def test_russian_skiy(self) -> None:
        """Русские фамилии на -ский."""
        self.assertEqual(decline_lastname("Достоевский", "female", "ru"), "Достоевская")
        self.assertEqual(decline_lastname("Чайковский", "female", "ru"), "Чайковская")

    def test_russian_oy(self) -> None:
        """Русские фамилии на -ой."""
        self.assertEqual(decline_lastname("Толстой", "female", "ru"), "Толстая")

    def test_female_already_declined(self) -> None:
        """Женские фамилии в правильной форме не изменяются."""
        self.assertEqual(decline_lastname("Иванова", "female", "ru"), "Иванова")
        self.assertEqual(decline_lastname("Достоевская", "female", "ru"), "Достоевская")
        self.assertEqual(decline_lastname("Толстая", "female", "ru"), "Толстая")

    def test_unchanged_endings(self) -> None:
        """Фамилии на -ко, -енко, -ич, -ых, -их не склоняются."""
        self.assertEqual(decline_lastname("Шевченко", "female", "ru"), "Шевченко")
        self.assertEqual(decline_lastname("Петрых", "female", "ru"), "Петрых")
        self.assertEqual(decline_lastname("Черных", "female", "ru"), "Черных")

    def test_empty_input(self) -> None:
        """Пустой ввод возвращает None или исходное значение."""
        self.assertIsNone(decline_lastname("", "female", "ru"))
        self.assertIsNone(decline_lastname(None, "female", "ru"))

    def test_unknown_culture(self) -> None:
        """Для неизвестной культуры фамилия не склоняется."""
        self.assertEqual(decline_lastname("Smith", "female", "en"), "Smith")
