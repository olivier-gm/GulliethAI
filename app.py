from flask import Flask, render_template, request, redirect, url_for, send_file, session
import threading
import os
import logging
from dotenv import load_dotenv
from form_processor import FormProcessor
from algorythms import Document_process
from IA import generate_essay_content, generate_introduction, generate_conclusion, validate_titles

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', '7f8b9a2c3d4e5f608192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8')
@app.route('/')
def welcome():
    return render_template('main_page.html') 

@app.route('/bach')
def show_form_bach():
    session.clear()
    return render_template('bachiller.html')

@app.route('/process_form_bach', methods=['POST'])
def process_form_bach():
        # Retrieve form data
    form_data = request.form
    processor = FormProcessor(form_data, 'bach')
    processor.process()
    replacements, head_title = processor.generate_replacements()
    introduccion = processor.introduccion
    body = processor.body
    #body = generate_essay_content(processor.title)
    #if body != '':
        #introduccion = generate_introduction(processor.title, body)
    conclusion = processor.conclusion

    input_doc='input/plantilla_bach.docx'
    input_doc2='input/plantilla_bachempty.docx'

  # Check if the file exists
    random_code = ''
    if os.path.isfile(f'output/{head_title}.docx'):
        # If the file exists, generate a random code and append it to the filename
        random_code = '_' + Document_process.generate_random_code()
    docx_output = f'output/{head_title}{random_code}.docx'
    
    university_name = form_data.get('u', '')
    Document_process.fill_placeholders(docx_output, input_doc, input_doc2, replacements,
                                        introduccion, body, conclusion, head_title, 'bach',
                                        university_name=university_name)

    session['file_generated'] = True

    # Redirect to a new page or indicate success
    return redirect(url_for('choose_file', filename=head_title + random_code))
    #return redirect(url_for('index'))

@app.route('/form')
def show_form():
    session.clear()
    return render_template('universitario.html')

@app.route('/process_form', methods=['POST'])
def process_form():

    form_data = request.form
    processor = FormProcessor(form_data, 'uni')
    processor.process()
    replacements, head_title = processor.generate_replacements()
    #introduccion = processor.introduccion
    #body = processor.body
    body = ''
    if validate_titles(processor.formatted_title).startswith('TRUE'):
        body = generate_essay_content(processor.title, processor.subtitles)

    else:

        return redirect(url_for('welcome'))  # Redirect to the form if the file wasn't generated
    introduccion = ''
    conclusion = ''
    if body != '':
        introduccion = generate_introduction(processor.title, body)
        conclusion = generate_conclusion(processor.title, body)
        #conclusion = processor.conclusion

    input_doc='input/plantilla.docx'
    input_doc2='input/plantillaempty.docx'
    # Check if the file exists
    random_code = ''
    if os.path.isfile(f'output/{head_title}.docx'):
        # If the file exists, generate a random code and append it to the filename
        random_code = '_' + Document_process.generate_random_code()
    docx_output = f'output/{head_title}{random_code}.docx'
    university_name = form_data.get('u', '')
    Document_process.fill_placeholders(docx_output, input_doc, input_doc2, replacements,
                                        introduccion, body, conclusion, head_title, 'uni',
                                        university_name=university_name)

    session['file_generated'] = True

    # Redirect to a new page or indicate success
    return redirect(url_for('choose_file', filename=head_title + random_code))
    #return redirect(url_for('index'))


@app.route('/choose_file/<filename>')
def choose_file(filename):
    """Renders the file download page."""
    if 'file_generated' not in session:
        return redirect(url_for('welcome'))  # Redirect to the form if the file wasn't generated
        # Schedule the file removal after a delay
    file_path = f'output/{filename}.docx'
    threading.Timer(7800, Document_process.remove_file, args=[file_path]).start()
    return render_template('download.html', filename=filename)

@app.route('/download_file/<filename>/<filetype>')
def download_file(filename, filetype):
    if 'file_generated' not in session:
        return redirect(url_for('welcome'))
    file_path = f'output/{filename}.{filetype}'
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        logging.error('Error descargando archivo: %s', e)
        return render_template('404.html')


@app.errorhandler(404)
def page_not_found(e):
    # note that we set the 404 status explicitly
    return render_template('404.html')


if __name__ == '__main__':
    app.run(debug=True)