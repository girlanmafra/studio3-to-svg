from flask import Flask, request, send_file, render_template_string
import zipfile
import tempfile
import os
import xml.etree.ElementTree as ET

app = Flask(__name__)

HTML_FORM = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Studio to SVG Converter</title>
</head>
<body>
    <h1>Convert .studio/.studio3 to SVG</h1>
    <form method="POST" enctype="multipart/form-data" action="/convert">
        <input type="file" name="studio_file" accept=".studio,.studio3" required>
        <button type="submit">Convert to SVG</button>
    </form>
</body>
</html>
'''

def studio_to_svg(studio_file_path, output_svg_path):
    try:
        with zipfile.ZipFile(studio_file_path, 'r') as archive:
            for name in archive.namelist():
                if name.endswith('.xml'):
                    xml_data = archive.read(name)
                    root = ET.fromstring(xml_data)

                    svg_elements = []
                    for shape in root.findall(".//Shape"):
                        path_data = shape.findtext("PathData")
                        color = shape.findtext("StrokeColor") or "#000000"
                        if path_data:
                            svg_elements.append(
                                f'<path d="{path_data}" stroke="{color}" fill="none"/>'
                            )

                    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" version="1.1">
{''.join(svg_elements)}
</svg>'''

                    with open(output_svg_path, 'w') as f:
                        f.write(svg_content)
                    return True
    except Exception as e:
        print("Error:", e)
    return False

@app.route('/', methods=['GET'])
def index():
    return render_template_string(HTML_FORM)

@app.route('/convert', methods=['POST'])
def convert():
    if 'studio_file' not in request.files:
        return "No file uploaded", 400

    file = request.files['studio_file']
    if file.filename == '':
        return "No selected file", 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=".studio") as temp_input, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".svg") as temp_output:

        file.save(temp_input.name)
        success = studio_to_svg(temp_input.name, temp_output.name)

        if not success:
            return "Failed to convert file. Make sure it's a valid .studio/.studio3 file.", 500

        return send_file(temp_output.name, as_attachment=True, download_name="converted.svg")

if __name__ == '__main__':
    app.run(debug=True)
