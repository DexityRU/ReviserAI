from flask import Flask, session, request, render_template, redirect, url_for
import pathlib
import os
import pytesseract
import minecart
import fitz
import traceback
import json
import pycurl
from transliterate import translit
from io import BytesIO

app = Flask(__name__)
DEBUG = False

groups = {
    "Бухгалтерская отчетность Форма 1": "4f501f4a-c665-4cc8-9715-6ed26e7819f2",
    "Устав": "33a37ce4-c6a9-4dad-8424-707abd47c125",
    "Положение о СД": "555ced1c-c169-4d61-9a82-348801494581",
    "Бухгалтерская отчетность Форма 2": "cabd193c-f9a9-4a9c-a4ae-80f0347adf40",
    "Аудиторское заключение": "16f35ccc-b90f-4731-8178-11f3e0e3ca20",
    "Описание деятельности ГК": "a397c2cf-c5ad-4560-bc65-db4f79840f82",
    "Решение назначение ЕИО": "3af37c7f-d8b1-46de-98cc-683b0ffb3513",
    "Неизвестный файл": None,
    None: None
}

files = []

if DEBUG:
    pytesseract.pytesseract.tesseract_cmd = r'D:\Tesseract\tesseract.exe'


def send_file(path, ident=None, inn=None):
    url = "http://elib-hackathon.psb.netintel.ru/elib/api/service/documents"

    headers = ["Accept: */*",
               "Content-Type: multipart/form-data",
               "Authorization: Basic TXVsY2liZXJ1czpNdWxjaWJlcnVzNkc5"]

    filename = os.path.basename(path)

    payload = dict()
    payload['unrecognized'] = True
    print(ident)
    if ident:
        payload["documentNomenclatureId"] = ident
        payload['unrecognized'] = False
    if inn:
        payload["inn"] = inn

    payload = ("createRequest", json.dumps(payload))

    buffer = BytesIO()

    c = pycurl.Curl()
    c.setopt(c.URL, url)
    c.setopt(pycurl.HTTPHEADER, headers)
    c.setopt(c.HTTPPOST, [
        ('attachments', (
            c.FORM_FILE, path,
            c.FORM_FILENAME, filename,
            c.FORM_CONTENTTYPE, 'application/pdf',
        )),
        payload
    ])
    c.setopt(c.WRITEDATA, buffer)
    c.perform()

    response_code = c.getinfo(pycurl.RESPONSE_CODE)

    if DEBUG:
        print("\n[DEBUG] RESPONSE CODE: " + str(response_code) + "\n")
    c.close()

    return response_code, json.loads(buffer.getvalue().decode("utf-8"))


def classify(file, path):
    data_from_image = ""
    doc = minecart.Document(file)
    try:
        page = doc.get_page(0)
        im = page.images[0].as_pil()
        data_from_image += pytesseract.image_to_string(im, lang='rus').lower() + "\n"
    except Exception as e:
        if DEBUG:
            print("[PDF WITH NO IMAGES]")
            traceback.print_exc()
            print(e)
    del doc
    document = fitz.open(path)
    data_from_image += document[0].getText()
    document.close()
    del document
    data_from_image = data_from_image.lower()

    if any([word in data_from_image for word in
            ["бухгалтерский баланс", "0710001", "актив", "пассив", "окуд", "окпо", "баланс"]]):
        group = "Бухгалтерская отчетность Форма 1"
    elif any([word in data_from_image for word in
              ["устав", "органы управления", "резервный фонд", "бюллетени", "редакция"]]):
        group = "Устав"
    elif any([word in data_from_image for word in
              ["отчет о финансовых результатах", "0710002", "чистая прибыль",
               "налог на прибыль", "финансовых резулдьтатах", "январь - март"]]):
        group = "Бухгалтерская отчетность Форма 2"
    elif any([word in data_from_image for word in
              ["аудиторское заключение", "сведения об аудируемом лице", "сведения об аудиторе",
               "основание для выражения мнения", "ответственность аудитора"]]):
        group = "Аудиторское заключение"
    elif any([word in data_from_image for word in
              ["положение о совете директоров", "председатель совета директоров", "письменное мнение",
               "опросный лист", "уведомление о проведении совета директоров", "о совете директоров"]]):
        group = "Положение о СД"
    elif any([word in data_from_image for word in
              ["презентация компании", "история компании", "обзор рынка",
               "обзор компании", "уведомление о проведении совета директоров"]]):
        group = "Описание деятельности ГК"
    elif any([word in data_from_image for word in
              ["совета директоров", "дата составления протокола", "назначение генерального директора",
               "избрание генерального директора", "итоги голосования", "принятое решение"]]):
        group = "Решение назначение ЕИО"
    else:
        group = "Неизвестный файл"
    return group


@app.route("/", methods=["GET", "POST"])
def index():
    group = None
    error = None
    success = None
    ident = None
    new_filename = None
    inn = None
    if request.method == "POST":
        inn = request.form.get("inn")
        file = request.files.get('input_file')
        if type(inn) == str:
            if not (inn.isdigit() and len(inn) == 10) and len(inn) != 0:
                error = "Введён некорректный ИНН!"
            if file and not error:
                filename = file.filename
                if filename.lower().split(".")[-1] != "pdf":
                    error = "В данный момент, поддерживаются только файлы формата PDF!"
                else:
                    upload_dir = str(pathlib.Path(__file__).parent.resolve()) + "/uploads/"
                    path = upload_dir + filename
                    file.save(path)
                    file_for_work = open(path, 'rb')
                    try:
                        group = classify(file_for_work, path)
                        file_for_work.close()
                        new_filename = translit(group + ".pdf", "ru", reversed=True)
                        os.rename(upload_dir + filename, upload_dir + new_filename)
                        path = upload_dir + new_filename
                        if group != "Неизвестный файл":
                            res = send_file(path, ident=groups[group], inn=inn)
                            if DEBUG:
                                print(res[1])
                            ident = res[1]["id"]
                            if res[0] != 200:
                                error = f"При отправке файла на сервер произошла ошибка - {res[0]}"
                            else:
                                success = "Файл успешно загружен на сервер!"
                        else:
                            error = "Файл не был отправлен на сервер, поскольку его тип неизвестен"
                    except Exception as e:
                        if DEBUG:
                            traceback.print_exc()
                        error = e
                    file_for_work.close()
                    os.remove(path)
            else:
                error = "Файл не был загружен!"
    return render_template("index.html", classification_group=group, error=error, success=success,
                           filename=new_filename, group=group, id=ident, inn=inn, group_id=groups[group])


@app.route("/path", methods=["GET", "POST"])
def path_page():
    error = None
    return render_template("path.html", error=error)


@app.route("/result")
def result_page():
    global files
    warning_cases = 0
    success_cases = 0
    wrong_cases = 0
    for file in files:
        if file['tag'] == "no-class":
            warning_cases += 1
        elif file['tag'] == "wrong-file":
            wrong_cases += 1
        else:
            success_cases += 1
    return render_template("result.html", success_docs=success_cases, warning_docs=warning_cases, wrong_docs=wrong_cases, files=files)


def check_files(path=None):
    global files
    if path is None:
        path = str(pathlib.Path(__file__).parent.resolve()) + "/playground"
    for file in os.listdir(path):
        file_struct = dict()
        file_struct['old_filename'] = file
        file_path = path + "/" + file
        if os.path.isfile(file_path):
            if file.split(".")[-1].lower() == "pdf":
                file_for_work = open(file_path, 'rb')
                try:
                    group = classify(file_for_work, file_path)
                    file_for_work.close()
                    new_filename = translit(group + ".pdf", "ru", reversed=True)
                    try:
                        os.rename(path + "/" + file, path + "/" + new_filename)
                    except FileExistsError as e:
                        pass
                    file_path = path + "/" + new_filename
                    if group != "Неизвестный файл":
                        file_struct['filename'] = new_filename
                        res = send_file(file_path, ident=groups[group])
                        if res[0] != 200:
                            file_struct['id'] = None
                            file_struct['tag'] = 'wrong-file'
                        else:
                            file_struct['id'] = res[1]['id']
                            file_struct['tag'] = group
                            file_struct['tag_id'] = groups[group]
                    else:
                        file_struct['filename'] = file
                        file_struct['id'] = None
                        file_struct['tag'] = 'no-class'
                except Exception as e:
                    file_struct['filename'] = file
                    file_struct['id'] = None
                    file_struct['tag'] = 'wrong-file'
                    if DEBUG:
                        traceback.print_exc()
                file_for_work.close()
            else:
                file_struct['filename'] = file
                file_struct['id'] = None
                file_struct['tag'] = 'wrong-file'
            files.append(file_struct)
        else:
            new_path = translit(file_path, "ru", reversed=True)
            os.rename(file_path, new_path)
            check_files(new_path)


if __name__ == '__main__':
    if DEBUG:
        os.system("xcopy playground_state playground /E /C /I /Y")
    else:
        os.system("cp -r playground_state/* playground/")
    check_files()
    if not os.path.exists("uploads"):
        os.mkdir("uploads")
    if DEBUG:
        app.run("0.0.0.0", 5000)
    else:
        app.run("0.0.0.0", 80)
