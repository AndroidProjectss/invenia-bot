import io
import unittest
import zipfile
from unittest.mock import patch

from pypdf import PdfWriter
from bot.media import question_from_file, MediaError, MAX_FILE_BYTES, bounded_read


class DocumentRecognitionTest(unittest.TestCase):
    def test_text_with_caption_preserves_question_and_contents(self):
        result = question_from_file('Ошибка подключения интернета'.encode(), 'text/plain', 'document', caption='Что делать?')
        self.assertIn('Что делать?', result)
        self.assertIn('Ошибка подключения интернета', result)

    def test_docx_reads_paragraphs_without_ai(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="urn:test"><w:p><w:r><w:t>Интернет иштебейт</w:t></w:r></w:p></w:document>')
        with patch('bot.media.read_media', side_effect=AssertionError('Не нужен ИИ')):
            result = question_from_file(buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'document')
        self.assertIn('Интернет иштебейт', result)

    def test_scanned_pdf_uses_recognition(self):
        writer=PdfWriter();writer.add_blank_page(width=100,height=100)
        buffer=io.BytesIO();writer.write(buffer)
        with patch('bot.media.read_media', return_value='Как проверить баланс?') as recognition:
            result=question_from_file(buffer.getvalue(),'application/pdf','document')
        self.assertEqual(result,'Как проверить баланс?')
        recognition.assert_called_once()

    def test_encrypted_pdf_has_actionable_error(self):
        writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.encrypt('password')
        buffer=io.BytesIO();writer.write(buffer)
        with self.assertRaisesRegex(MediaError, 'паролем'):
            question_from_file(buffer.getvalue(),'application/pdf','document')

    def test_download_is_bounded(self):
        with self.assertRaisesRegex(MediaError, '12 МБ'):
            bounded_read(io.BytesIO(b'x'*(MAX_FILE_BYTES+1)))

    def test_unknown_format_is_not_sent_to_model(self):
        with patch('bot.media.read_media') as recognition:
            with self.assertRaises(MediaError):
                question_from_file(b'unknown', 'application/x-executable', 'document')
        recognition.assert_not_called()

    def test_photo_retains_caption_instead_of_ignoring_image(self):
        with patch('bot.media.read_media',return_value='Ошибка APN') as recognition:
            result=question_from_file(b'photo','image/jpeg','image',caption='Почему нет интернета?')
        recognition.assert_called_once()
        self.assertIn('Ошибка APN',result)
        self.assertIn('Почему нет интернета?',result)
