import os
import re
import shutil
import zipfile
import pytest
from docx import Document
from algorythms import Document_process

# Assume current working directory during tests is the project root
TEMPLATE_PATH = 'Templates/Universitario.docx'
# La plantilla real de producción (con los placeholders '[title]', '[date]',
# etc.), a diferencia de TEMPLATE_PATH que es un docx dummy de relleno.
REAL_TEMPLATE_PATH = 'input/plantilla.docx'
TEST_OUTPUT_DIR = 'tests/output'
TEST_OUTPUT_DOCX = os.path.join(TEST_OUTPUT_DIR, 'test_output.docx')
TEST_OUTPUT_PDF = os.path.join('output', 'test_output.pdf') # hardcoded in app logic

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup
    os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)
    os.makedirs('output', exist_ok=True)
    
    # We must have a test template, if it doesn't exist we make a dummy one for tests
    if not os.path.exists(TEMPLATE_PATH):
        os.makedirs(os.path.dirname(TEMPLATE_PATH), exist_ok=True)
        doc = Document()
        # Add a dummy paragraph to avoid index out of bounds when replacing things on cover
        for i in range(40):
            doc.add_paragraph(f'Paragraph {i}')
        doc.save(TEMPLATE_PATH)
        
    yield
    
    # Teardown
    if os.path.exists(TEST_OUTPUT_DIR):
        shutil.rmtree(TEST_OUTPUT_DIR)
    
    for f in [TEST_OUTPUT_PDF]:
        if os.path.exists(f):
            os.remove(f)

def test_document_generation_with_toc_and_logo():
    replacements = {'[TITLE]': 'Test Title'}
    introduction = 'Test Intro\nSecond line'
    essay_content = 'Test Body'
    conclusion = 'Test Conclusion'
    
    # Run the main generation function with a university that has a test logo
    # Assuming 'Universidad Central de Venezuela' maps to a logo that exists or at least won't crash
    Document_process.fill_placeholders(
        docx_output=TEST_OUTPUT_DOCX, 
        template_path=TEMPLATE_PATH, 
        template_path2='', 
        replacements=replacements,
        introduction=introduction, 
        essay_content=essay_content, 
        conclusion=conclusion, 
        head_title='Test Heading', 
        id='uni',
        university_name='Universidad Central de Venezuela'
    )
    
    # Verify file was created
    assert os.path.exists(TEST_OUTPUT_DOCX), "Output DOCX was not generated."
    
    # Open the generated DOCX and inspect it
    doc = Document(TEST_OUTPUT_DOCX)
    
    # 1. Verify TOC field is present in the XML
    # Nota: doc.element.xml devuelve str, no bytes. Y si LibreOffice esta
    # instalado, el docx final pasa por el (para poblar el indice), que
    # reordena los switches del campo, asi que no se compara el literal exacto.
    xml_content = doc.element.xml
    assert 'w:fldChar' in xml_content, "TOC field was not added (fldChar missing)."

    instr = ' '.join(re.findall(r'<w:instrText[^>]*>([^<]*)</w:instrText>', xml_content))
    assert 'TOC' in instr, "TOC instruction text not found."
    assert '1-3' in instr, "El campo TOC deberia abarcar los niveles 1 a 3."

    # 2. Verify Headings are applied
    heading_found = False
    for p in doc.paragraphs:
        if p.style.name == 'Heading 1' and 'Test Heading' in p.text:
            heading_found = True
            break
    assert heading_found, "Heading 1 style was not correctly applied to body topic."

    # 3. Los encabezados deben declarar nivel de esquema; sin esto el indice
    #    sale vacio ("no se encontraron entradas de tabla de contenido").
    #    Puede estar en el parrafo (document.xml) o, si LibreOffice reescribio
    #    el archivo, en la definicion del estilo (styles.xml).
    with zipfile.ZipFile(TEST_OUTPUT_DOCX) as z:
        styles_xml = z.read('word/styles.xml').decode('utf-8')
    assert 'w:outlineLvl' in xml_content or 'outlineLvl' in styles_xml, \
        "Los encabezados no declaran nivel de esquema: el indice saldria vacio."

def test_logo_insertion_unknown_university():
    # Should not crash if the university is unknown and has no logo
    Document_process.fill_placeholders(
        docx_output=TEST_OUTPUT_DOCX, 
        template_path=TEMPLATE_PATH, 
        template_path2='', 
        replacements={},
        introduction='', 
        essay_content='Body only', 
        conclusion='', 
        head_title='Title',
        id='uni',
        university_name='Unknown University XYZ'
    )
    assert os.path.exists(TEST_OUTPUT_DOCX), "Document should generate successfully even if logo is missing."


# ── Separacion de parrafos y deteccion de subtitulos ───────────────────
# El modelo separa los parrafos con '\n\n\n'; antes esa separacion se perdia
# y todo el texto quedaba pegado en el documento.

def test_split_blocks_respeta_la_separacion_del_modelo():
    body = "Primer parrafo.\n\n\nUn Subtitulo\n\n\nSegundo parrafo."
    assert Document_process._split_blocks(body) == [
        'Primer parrafo.', 'Un Subtitulo', 'Segundo parrafo.',
    ]


def test_split_blocks_con_saltos_simples():
    # Si el modelo no deja lineas en blanco, se separa por saltos simples
    body = "Primer parrafo.\nSegundo parrafo."
    assert Document_process._split_blocks(body) == [
        'Primer parrafo.', 'Segundo parrafo.',
    ]


def test_split_blocks_con_separadores_mezclados():
    # El modelo no es consistente: mezcla '\n' y '\n\n\n' en un mismo texto
    body = "Uno.\nDos.\n\n\nTres.\r\n\r\nCuatro."
    assert Document_process._split_blocks(body) == [
        'Uno.', 'Dos.', 'Tres.', 'Cuatro.',
    ]


@pytest.mark.parametrize('linea', [
    'Origen y Fundamentos del Bitcoin',
    'Adopcion Institucional y Marcos Regulatorios',
    'Membrana Plasmatica:',
    '**Subtitulo en negrita**',
    '## Subtitulo markdown',
    # Un subtitulo puede cerrar con parentesis: antes se descartaban y no
    # salian ni en negrita ni en el indice
    'Capa 1 (Layer 1): La Cadena Principal (On-Chain)',
    'Capa 2 (Layer 2): Soluciones de Escalabilidad (Off-Chain)',
])
def test_detecta_subtitulos(linea):
    assert Document_process._is_subtitle(linea)


@pytest.mark.parametrize('linea', [
    'El Bitcoin, introducido en 2008 bajo el seudonimo de Satoshi Nakamoto, representa la primera '
    'implementacion exitosa de una moneda digital descentralizada.',
    'La arquitectura combina criptografia asimetrica y teoria de juegos.',
    'Una frase corta que termina en punto.',
    # Cierra con parentesis pero la frase termina en punto: sigue siendo parrafo
    'Esto es un ejemplo entre parentesis (con cierre.)',
])
def test_no_confunde_parrafos_con_subtitulos(linea):
    assert not Document_process._is_subtitle(linea)


def test_limpia_marcadores_markdown():
    assert Document_process._clean_markdown('## Titulo') == 'Titulo'
    assert Document_process._clean_markdown('**Titulo**') == 'Titulo'


# ── Portada de una sola página: título centrado, fecha al pie ──────────
# El título y la fecha se anclan con w:framePr a una posición absoluta de
# la página (independiente del logo, el largo del nombre de la universidad
# o la cantidad de integrantes). Los 22 párrafos en blanco que antes
# simulaban ese centrado ya no hacen falta y se recortan a uno solo, cuya
# altura se calcula para que el pie de página nunca choque con el título
# ni se desborde a una segunda página.

def test_trim_cover_spacers_reduce_los_parrafos_en_blanco():
    doc = Document(REAL_TEMPLATE_PATH)
    title_para = Document_process._find_paragraph(doc, '[title]', exact=True)
    assert title_para is not None

    blancos_antes = sum(1 for p in doc.paragraphs if p.text.strip() == '')
    Document_process._trim_cover_spacers(doc, title_para, has_logo=False, university_name='UCV')
    blancos_despues = sum(1 for p in doc.paragraphs if p.text.strip() == '')

    # Sólo debe quedar un párrafo en blanco (el espaciador calculado).
    assert blancos_despues == 1
    assert blancos_despues < blancos_antes


@pytest.mark.parametrize('has_logo,university_name,esperado_pt', [
    (False, 'UCV', 290),      # sin logo, nombre corto: espaciador grande
    (True, 'UCV', 204),       # con logo: menos espaciador (el logo ya empuja)
    (False, 'U' * 60, 274),   # nombre largo (2 lineas): un poco menos
    (True, 'U' * 60, 188),    # logo + nombre largo: el que menos necesita
])
def test_trim_cover_spacers_calcula_el_espaciador_segun_encabezado(
    has_logo, university_name, esperado_pt
):
    # Los valores esperados salen de la misma fórmula que usa el código
    # (_TITLE_CLEAR_ZONE_PT menos lo que ya empuja el encabezado hacia
    # abajo); lo que importa no es memorizar constantes sino que el
    # espaciador SIEMPRE se reduzca a medida que el logo y/o el nombre
    # largo ya empujan el encabezado: si no se reduce, el pie de página se
    # desborda a una segunda página cuando además hay muchos integrantes
    # (bug real que motivó este ajuste).
    doc = Document(REAL_TEMPLATE_PATH)
    title_para = Document_process._find_paragraph(doc, '[title]', exact=True)
    Document_process._trim_cover_spacers(
        doc, title_para, has_logo=has_logo, university_name=university_name,
    )
    spacer = next(p for p in doc.paragraphs if p.text.strip() == '')
    space_after_pt = spacer.paragraph_format.space_after.pt
    assert abs(space_after_pt - esperado_pt) < 5


def test_trim_cover_spacers_con_logo_y_nombre_largo_reserva_lo_minimo():
    """El caso con más 'empuje' propio (logo + nombre largo) debe ser el
    que menos espaciador artificial necesite de los cuatro combinados."""
    resultados = {}
    for has_logo in (False, True):
        for nombre_largo in (False, True):
            doc = Document(REAL_TEMPLATE_PATH)
            title_para = Document_process._find_paragraph(doc, '[title]', exact=True)
            uni = 'U' * 60 if nombre_largo else 'UCV'
            Document_process._trim_cover_spacers(
                doc, title_para, has_logo=has_logo, university_name=uni,
            )
            spacer = next(p for p in doc.paragraphs if p.text.strip() == '')
            resultados[(has_logo, nombre_largo)] = spacer.paragraph_format.space_after.pt

    assert resultados[(True, True)] < resultados[(False, False)]
    assert resultados[(True, False)] < resultados[(False, False)]
    assert resultados[(False, True)] < resultados[(False, False)]


def test_insert_logo_devuelve_false_si_no_encuentra_el_logo():
    doc = Document(REAL_TEMPLATE_PATH)
    assert Document_process.insert_logo(doc, 'Universidad Inexistente XYZ') is False


def test_insert_logo_devuelve_true_si_lo_encuentra():
    doc = Document(REAL_TEMPLATE_PATH)
    assert Document_process.insert_logo(doc, 'Universidad Central de Venezuela') is True


def test_underline_words_no_borra_el_logo():
    """Regresión: reconstruir los runs de TODOS los párrafos (para
    subrayar palabras clave) borraba el run del logo aunque no tuviera
    texto, porque run.clear() elimina cualquier contenido, incluida una
    imagen. Ahora sólo se tocan párrafos que sí contienen alguna palabra."""
    doc = Document(REAL_TEMPLATE_PATH)
    Document_process.insert_logo(doc, 'Universidad Central de Venezuela')
    Document_process.underline_words_in_first_page(
        doc, ['DOCENTE:', 'ALUMNOS:', 'ALUMNO:', 'SECCION:', 'MATERIA:']
    )
    assert Document_process._has_drawing(doc.paragraphs[0])


def test_fill_placeholders_caso_extremo_no_lanza_excepcion():
    """Universidad de nombre largo, todos los campos al máximo permitido
    por el formulario y los 8 integrantes llenos: no debe romper la
    generación (aunque no podemos medir el conteo real de páginas sin
    LibreOffice instalado, al menos la construcción del documento no debe
    fallar)."""
    reps = {
        '[u]': 'U' * 80, '[area]': 'A' * 40, '[carrera]': 'C' * 40,
        '[city]': 'CARACAS, ', '[date]': '20 DE AGOSTO DE 2026',
        '[seccion]': 'SECCION: "X"', '[title]': 'TITULO DE PRUEBA',
        '[docente]': 'DOCENTE:', '[teacher]': 'T' * 60,
        '[asignatura]': 'M' * 60, '[asignatura2]': '', '[asignatura_t]': 'MATERIA: ',
        '[periodo]': '', '[academico]': 'SEMESTRE: ', '[academico2]': '', '[periodo2]': '',
        '[alumnos]': 'ALUMNOS:',
    }
    for i in range(1, 9):
        reps[f'[{i}]'] = 'ESTUDIANTE ' * 3
        reps[f'[id{i}]'] = ' C.I- 1234567890'

    out = os.path.join(TEST_OUTPUT_DIR, 'extreme.docx')
    Document_process.fill_placeholders(
        out, REAL_TEMPLATE_PATH, '', reps, '', '', '', 'Cuerpo', 'uni',
        university_name='Universidad Central de Venezuela',
    )
    assert os.path.exists(out)
