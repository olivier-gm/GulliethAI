import os
import shutil
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
    xml_content = doc.element.xml
    assert b'w:fldChar' in xml_content, "TOC field was not added (fldChar missing)."
    assert b'TOC \\o "1-2" \\h \\z \\u' in xml_content or b'TOC \\o &quot;1-2&quot; \\h \\z \\u' in xml_content, "TOC instruction text not found."
    assert b'w:updateFields' in xml_content, "updateFields for TOC refresh not found."
    
    # 2. Verify Headings are applied
    heading_found = False
    for p in doc.paragraphs:
        if p.style.name == 'Heading 1' and 'Test Heading' in p.text:
            heading_found = True
            break
    assert heading_found, "Heading 1 style was not correctly applied to body topic."

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
