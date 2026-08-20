import os
import re
import shutil
import zipfile
import pytest
from docx import Document
from algorythms import Document_process

# Assume current working directory during tests is the project root
TEMPLATE_PATH = 'Templates/Universitario.docx'
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
