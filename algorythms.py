import subprocess
import os
import string
import random
import shutil
import logging
import unicodedata
import re

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

logger = logging.getLogger(__name__)


class Document_process:

    # ── LibreOffice detection ──────────────────────────────────────────

    @staticmethod
    def _find_libreoffice():
        """Busca la ruta de LibreOffice en ubicaciones comunes."""
        possible_paths = [
            'C:/Program Files/LibreOffice/program/soffice.exe',
            'C:/Program Files (x86)/LibreOffice/program/soffice.exe',
            '/usr/bin/soffice',
            '/usr/local/bin/soffice',
        ]
        for path in possible_paths:
            if os.path.isfile(path):
                return path
        # Intentar con PATH del sistema
        found = shutil.which('soffice')
        if found:
            return found
        raise FileNotFoundError(
            "LibreOffice no encontrado. Instálalo o agrega 'soffice' al PATH."
        )

    @staticmethod
    def convert(input_file, output_folder):
        """Convierte un DOCX a PDF usando LibreOffice en modo headless."""
        try:
            libre_path = Document_process._find_libreoffice()
        except FileNotFoundError as e:
            logger.error(str(e))
            return

        commandStrings = [
            libre_path, "--headless", "--convert-to",
            "pdf", "--outdir", output_folder, input_file
        ]
        try:
            retCode = subprocess.call(commandStrings, timeout=120)
            if retCode == 0:
                logger.info('Conversión a PDF exitosa: %s', input_file)
            else:
                logger.error('Error en conversión a PDF. Código: %d', retCode)
        except subprocess.TimeoutExpired:
            logger.error('Timeout al convertir a PDF: %s', input_file)
        except Exception as e:
            logger.error('Error inesperado en conversión: %s', e)

    # ── Paragraph helpers ──────────────────────────────────────────────

    @staticmethod
    def delete_paragraph(paragraph):
        p = paragraph._element
        p.getparent().remove(p)
        p._p = p._element = None

    @staticmethod
    def llenar_campos(replacements, document):
        """Reemplaza placeholders preservando el formato de los runs."""
        for paragraph in document.paragraphs:
            for key, value in replacements.items():
                if key in paragraph.text:
                    for run in paragraph.runs:
                        if key in run.text:
                            run.text = run.text.replace(key, value)

    @staticmethod
    def capitalizar_frases(cadena):
        palabras = cadena.split()
        palabras_capitalizadas = []
        skip_words = ['de', 'del', 'la', 'las', 'los', 'y', 'para']
        for palabra in palabras:
            if palabra.lower() in skip_words and palabras_capitalizadas:
                palabras_capitalizadas.append(palabra.lower())
            else:
                palabras_capitalizadas.append(palabra.capitalize())
        return ' '.join(palabras_capitalizadas)

    @staticmethod
    def generate_random_code(length=2):
        letters_and_digits = string.ascii_letters + string.digits
        return ''.join(random.choice(letters_and_digits) for i in range(length))

    @staticmethod
    def docx_replace(doc, old_text, new_text):
        for p in doc.paragraphs:
            if old_text in p.text:
                inline = p.runs
                for i in range(len(inline)):
                    if old_text in inline[i].text:
                        text = inline[i].text.replace(old_text, new_text)
                        inline[i].text = text

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    Document_process.docx_replace(cell, old_text, new_text)

    @staticmethod
    def remove_file(file_path):
        base_path = os.path.splitext(file_path)[0]
        for extension in ['.pdf', '.docx']:
            try:
                os.remove(base_path + extension)
                logger.info('Archivo eliminado: %s%s', base_path, extension)
            except Exception as error:
                logger.warning("Error eliminando archivo: %s", error)

    # ── TOC (Tabla de Contenido) ───────────────────────────────────────

    @staticmethod
    def _configure_heading_styles(document):
        """Configura los estilos Heading 1 y Heading 2 para el documento."""
        for heading_name in ['Heading 1', 'Heading 2']:
            try:
                style = document.styles[heading_name]
            except KeyError:
                # Si no existe, crearlo basándose en Normal
                from docx.enum.style import WD_STYLE_TYPE
                style = document.styles.add_style(heading_name, WD_STYLE_TYPE.PARAGRAPH)

            font = style.font
            font.name = 'Arial'
            font.size = Pt(14) if heading_name == 'Heading 1' else Pt(12)
            font.bold = True
            font.color.rgb = RGBColor(0, 0, 0)

    @staticmethod
    def add_toc_page(document):
        """Inserta una página de Tabla de Contenido usando campos OOXML nativos."""
        # Título "Índice"
        p_title = document.add_paragraph()
        p_title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        p_title.paragraph_format.line_spacing = Pt(21)
        run_title = p_title.add_run('Índice')
        run_title.bold = True
        run_title.font.size = Pt(16)
        run_title.font.name = 'Arial'

        # Espacio
        document.add_paragraph('')

        # Campo TOC nativo de Word/LibreOffice
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.line_spacing = Pt(21)

        # Begin field char
        run1 = paragraph.add_run()
        fldChar_begin = OxmlElement('w:fldChar')
        fldChar_begin.set(qn('w:fldCharType'), 'begin')
        run1._r.append(fldChar_begin)

        # Instruction text
        run2 = paragraph.add_run()
        instrText = OxmlElement('w:instrText')
        instrText.set(qn('xml:space'), 'preserve')
        instrText.text = ' TOC \\o "1-2" \\h \\z \\u '
        run2._r.append(instrText)

        # Separate field char
        run3 = paragraph.add_run()
        fldChar_sep = OxmlElement('w:fldChar')
        fldChar_sep.set(qn('w:fldCharType'), 'separate')
        run3._r.append(fldChar_sep)

        # Placeholder text (shown before TOC is updated)
        run4 = paragraph.add_run('Actualice este campo para ver el índice (F9)')
        run4.font.color.rgb = RGBColor(128, 128, 128)
        run4.font.size = Pt(11)

        # End field char
        run5 = paragraph.add_run()
        fldChar_end = OxmlElement('w:fldChar')
        fldChar_end.set(qn('w:fldCharType'), 'end')
        run5._r.append(fldChar_end)

        # Salto de página después del TOC
        document.add_page_break()

    @staticmethod
    def set_update_fields(document):
        """Fuerza la actualización automática de campos al abrir el documento."""
        settings_element = document.settings.element
        update_fields = OxmlElement('w:updateFields')
        update_fields.set(qn('w:val'), 'true')
        settings_element.append(update_fields)

    # ── Logo universitario ─────────────────────────────────────────────

    @staticmethod
    def _normalize_logo_name(university_name):
        """Normaliza el nombre de la universidad a un nombre de archivo."""
        # Quitar acentos
        nfkd = unicodedata.normalize('NFKD', university_name)
        ascii_name = ''.join(c for c in nfkd if not unicodedata.combining(c))
        # Minúsculas y reemplazar espacios
        normalized = ascii_name.lower().strip()
        normalized = re.sub(r'[^a-z0-9]+', '_', normalized)
        normalized = normalized.strip('_')
        return normalized

    @staticmethod
    def insert_logo(document, university_name, logo_dir='static/logos'):
        """Inserta el logo de la universidad centrado en la parte superior del documento."""
        if not university_name or not university_name.strip():
            return

        normalized = Document_process._normalize_logo_name(university_name)
        logo_path = None

        # Buscar el logo con distintas extensiones
        for ext in ['png', 'jpg', 'jpeg', 'webp']:
            candidate = os.path.join(logo_dir, f'{normalized}.{ext}')
            if os.path.isfile(candidate):
                logo_path = candidate
                break

        if logo_path is None:
            logger.info('Logo no encontrado para universidad: %s (buscado como: %s)',
                        university_name, normalized)
            return

        try:
            # Insertar el logo al principio del documento, centrado
            # Tomamos el primer párrafo y lo usamos como ancla
            first_para = document.paragraphs[0]

            # Crear un nuevo párrafo ANTES del primer párrafo
            new_para = OxmlElement('w:p')
            # Configurar alineación centrada
            pPr = OxmlElement('w:pPr')
            jc = OxmlElement('w:jc')
            jc.set(qn('w:val'), 'center')
            pPr.append(jc)
            new_para.append(pPr)

            # Insertar antes del primer párrafo
            first_para._element.addprevious(new_para)

            # Ahora acceder al párrafo insertado a través de python-docx
            from docx.text.paragraph import Paragraph
            inserted_para = Paragraph(new_para, document)
            run = inserted_para.add_run()
            run.add_picture(logo_path, width=Cm(3))

            logger.info('Logo insertado: %s', logo_path)
        except Exception as e:
            logger.error('Error insertando logo: %s', e)

    # ── Generación de párrafos con estilos ─────────────────────────────

    @staticmethod
    def parrafos(body, document, topic, flag):
        """Agrega párrafos al documento con título como Heading para el TOC."""
        if body != '':
            # Título de sección con estilo Heading 1 (para que el TOC lo detecte)
            p = document.add_paragraph(topic)
            try:
                p.style = document.styles['Heading 1']
            except KeyError:
                pass  # Si no existe Heading 1, usar formato manual
            p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            p.paragraph_format.line_spacing = Pt(21)
            # Asegurar fuente Arial negrita para el heading
            for run in p.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(14)
                run.bold = True
                run.font.color.rgb = RGBColor(0, 0, 0)

            document.add_paragraph('').alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

            # Filtrar líneas vacías SIN mutar la lista durante iteración (bug fix)
            paragraphs = [line for line in body.split('\n') if line.strip()]

            for parrafo in paragraphs:
                p = document.add_paragraph(parrafo)
                p.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
                p.paragraph_format.line_spacing = Pt(21)

            Document_process.docx_replace(document, '\r', '')
            Document_process.docx_replace(document, '\n', '')

            if flag:
                document.add_page_break()

    # ── Underline helpers ──────────────────────────────────────────────

    @staticmethod
    def underline_words_in_first_page(doc, words):
        # Calcular rango seguro basado en la cantidad real de párrafos
        max_para = len(doc.paragraphs)
        start = min(24, max_para)
        end = min(37, max_para)

        for i in range(start, end):
            paragraph = doc.paragraphs[i]
            new_runs = []
            for run in paragraph.runs:
                found = False
                for word in words:
                    if word in run.text:
                        parts = run.text.split(word)
                        for part in parts[:-1]:
                            new_runs.append((part, run.bold, run.italic, run.underline))
                            new_runs.append((word, run.bold, run.italic, True))
                        new_runs.append((parts[-1], run.bold, run.italic, run.underline))
                        found = True
                        break
                if not found:
                    new_runs.append((run.text, run.bold, run.italic, run.underline))
            for run in paragraph.runs:
                run.clear()
            for text, bold, italic, underline in new_runs:
                run = paragraph.add_run(text)
                run.bold = bold
                run.italic = italic
                run.underline = underline

    # ── Main orchestration ─────────────────────────────────────────────

    @staticmethod
    def fill_placeholders(docx_output, template_path, template_path2, replacements,
                           introduction, essay_content, conclusion, head_title, id,
                           university_name=''):
        if id == 'bach':
            words = ['DOCENTE:', 'ALUMNOS:', 'ALUMNO:', 'MATERIA:']
        else:
            words = ['DOCENTE:', 'ALUMNOS:', 'ALUMNO:', 'SECCION:',
                     'AÑO:', 'SEMESTRE:', 'TRIMESTRE:', 'MATERIA:']

        document = Document(template_path)

        # Insertar logo de la universidad (centrado arriba en portada)
        Document_process.insert_logo(document, university_name)

        # Llenar campos de la plantilla
        Document_process.llenar_campos(replacements, document)
        Document_process.underline_words_in_first_page(document, words)

        # Configurar estilo Normal
        style = document.styles['Normal']
        font = style.font
        font.name = 'Arial'
        font.size = Pt(12)

        # Configurar estilos de Heading para el TOC
        Document_process._configure_heading_styles(document)

        # Tamaño del título principal en portada
        try:
            paragraph = document.paragraphs[17]
            if paragraph.runs:
                run = paragraph.runs[0]
                run.font.size = Pt(17.5)
        except (IndexError, AttributeError):
            logger.warning('No se pudo ajustar el tamaño del título en la portada')

        has_content = essay_content != '' or introduction != '' or conclusion != ''

        if has_content:
            # Insertar página de Tabla de Contenido
            Document_process.add_toc_page(document)

        flagi = False
        if essay_content != '' or conclusion != '':
            flagi = True

        flage = False
        if conclusion != '':
            flage = True

        Document_process.parrafos(introduction, document, 'Introducción', flagi)
        Document_process.parrafos(essay_content, document, head_title, flage)
        Document_process.parrafos(conclusion, document, 'Conclusión', False)

        # Forzar actualización de campos (TOC) al abrir
        if has_content:
            Document_process.set_update_fields(document)

        head_title = head_title.replace(':', '_')
        document.save(docx_output)
        Document_process.convert(docx_output, 'output')