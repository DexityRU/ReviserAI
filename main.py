from flask import Flask, request, render_template
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

# Создание объекта сервера и выбор конфигурации
app = Flask(__name__)
DEBUG = False

# Константа для определния уникальных записей по названию
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

# Переменная для кэша результата обхода (ускорение загрузки страницы прототипа)
files = []

if DEBUG:
    pytesseract.pytesseract.tesseract_cmd = r'D:\Tesseract\tesseract.exe'


# Функция для отправки файла на сервер при помощи POST запроса
# path - Путь файла
# ident - Идентификатор группы (из groups)
# inn - ИНН
def send_file(path, ident=None, inn=None):
    # Указывам адрес севрера
    url = "http://elib-hackathon.psb.netintel.ru/elib/api/service/documents"

    # Хэдеры
    headers = ["Accept: */*",
               "Content-Type: multipart/form-data",
               "Authorization: Basic TXVsY2liZXJ1czpNdWxjaWJlcnVzNkc5"]

    # Получаем название файла
    filename = os.path.basename(path)

    # Создаём данные формы
    payload = dict()
    payload['unrecognized'] = True
    print(ident)
    if ident:
        payload["documentNomenclatureId"] = ident
        payload['unrecognized'] = False
    if inn:
        payload["inn"] = inn

    payload = ("createRequest", json.dumps(payload))

    # Создаём буфер для получения ответа от сервера
    buffer = BytesIO()

    # Формируем и отправляем запрос при помощи cURL
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
    # Выполняем наш запрос
    c.perform()

    # Получаем код ответа сервера
    response_code = c.getinfo(pycurl.RESPONSE_CODE)

    if DEBUG:
        print("\n[DEBUG] RESPONSE CODE: " + str(response_code) + "\n")
    # Закрываем соединение
    c.close()

    # Возвращаем код ответа и сам ответ
    return response_code, json.loads(buffer.getvalue().decode("utf-8"))


# Функция для классификации файлов по маркерам
# file - открытый поток файла, открыт через open с параметром rb
# path - путь до файла
def classify(file, path):
    data_from_image = ""
    # Создаём объект minecart на основе потока
    doc = minecart.Document(file)
    # Получаем первую страницу и первую картинку с неё
    try:
        page = doc.get_page(0)
        im = page.images[0].as_pil()
        # При помощи tesseract определяем текст
        data_from_image += pytesseract.image_to_string(im, lang='rus').lower() + "\n"
    # Если не получилось, значит PDF без картинок
    except Exception as e:
        if DEBUG:
            print("[PDF WITH NO IMAGES]")
            traceback.print_exc()
            print(e)
    del doc

    # Читаем текст первой страницы через fitz
    document = fitz.open(path)
    data_from_image += document[0].getText()
    document.close()
    del document

    # Приводим весь текст в нижний регистр, чтобы проще было находить совпадения
    data_from_image = data_from_image.lower()

    # Классифицируем файл
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

    # Возвращаем строку - группу файла
    return group


# Главная страница
@app.route("/", methods=["GET", "POST"])
def index():
    # Задание стандартных пустых констант для render_template
    # (Нельзя передать несмуществующую переменную)
    group = None  # группа файла
    error = None  # сообщение об ошибке
    success = None  # сообщение об успехе загрузки файла на удалённый сервер
    ident = None  # идентификатор (из groups)
    new_filename = None  # новое имя файла
    inn = None  # ИНН

    # Если метод запроса POST, значит нам пришли данные с формы, которые нужно обработать
    if request.method == "POST":

        # Получаем ИНН и файл
        inn = request.form.get("inn")
        file = request.files.get('input_file')

        # Проверка на то, есть ли у нас пустое поле ИНН (если нам его вообще не передали
        # (следовательно, запрос пришёл не с сайта), запрос недействительный)
        if type(inn) == str:
            # Проверка на длину ИНН (должно быть 10 или 0 символов)
            # 10 - норма
            # 0 - значит, нам он неизвестен
            if not (inn.isdigit() and len(inn) == 10) and len(inn) != 0:
                error = "Введён некорректный ИНН!"
            if file and not error:
                filename = file.filename
                # Проверка на PDF файл
                if filename.lower().split(".")[-1] != "pdf":
                    error = "В данный момент, поддерживаются только файлы формата PDF!"
                else:
                    # Сохраняем файл в директорию uploads
                    upload_dir = str(pathlib.Path(__file__).parent.resolve()) + "/uploads/"
                    path = upload_dir + filename
                    file.save(path)
                    file_for_work = open(path, 'rb')
                    try:
                        # Классифицируем файл
                        group = classify(file_for_work, path)
                        file_for_work.close()
                        # Меняем название в соответствие с новой группой
                        # (транслит, поскольку pycurl не принимает utf-8, только ascii без кириллицы)
                        new_filename = translit(group + ".pdf", "ru", reversed=True)
                        os.rename(upload_dir + filename, upload_dir + new_filename)
                        # Также обновляем путь до "нового" файла
                        path = upload_dir + new_filename
                        # Если группа файла нам известна, отправляем на сервер
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
                    # Закрываем файл, и удаляем из временной директории
                    file_for_work.close()
                    os.remove(path)
            else:
                error = "Файл не был загружен!"
    # Рисуем шаблон страницы со всеми необходимыми данными
    return render_template("index.html", classification_group=group, error=error, success=success,
                           filename=new_filename, group=group, id=ident, inn=inn, group_id=groups[group])


# Страница с выбором пути
@app.route("/path", methods=["GET", "POST"])
def path_page():
    # Переменная для сообщений об ошибке
    # На будущее
    error = None
    return render_template("path.html", error=error)


# Страница с результатом прохода по файлам
@app.route("/result")
def result_page():
    global files  # Обращаемся к глобальному кэшу
    # Переменные для подсчёта результата прохода по файлам
    warning_cases = 0
    success_cases = 0
    wrong_cases = 0

    # Сам подсчёт
    for file in files:
        if file['tag'] == "no-class":
            warning_cases += 1
        elif file['tag'] == "wrong-file":
            wrong_cases += 1
        else:
            success_cases += 1

    # Рисуем шаблон на основе данных, которые получили
    return render_template("result.html", success_docs=success_cases, warning_docs=warning_cases, wrong_docs=wrong_cases, files=files)


# Рекурсивная функция обхода директорий для файлов
def check_files(path=None):
    global files
    # Если директория не задана, задаём стандартное начальное значение
    if path is None:
        path = str(pathlib.Path(__file__).parent.resolve()) + "/playground"

    # Цикл обхода файлов и папок в директории
    for file in os.listdir(path):
        # Задаём словарь для информации о файле
        file_struct = dict()
        # Сохраняем старое название файла до изменения
        file_struct['old_filename'] = file
        file_path = path + "/" + file
        if os.path.isfile(file_path):
            # Проверка на тип файла, является ли PDF
            if file.split(".")[-1].lower() == "pdf":
                file_for_work = open(file_path, 'rb')
                try:
                    # Классифицируем документ
                    group = classify(file_for_work, file_path)
                    file_for_work.close()
                    # Переименовываем файл на транслит, чтобы pycurl смог отправить данные на сервер
                    # (Принимает только ascii названия)
                    new_filename = translit(group + ".pdf", "ru", reversed=True)
                    # Поскольку файлы не удаляются при проходе (как во временной директории upload),
                    # но стараются быть переименованными,
                    # нужна проверка на ошибку переименования, файл с таким названием уже может существовать
                    try:
                        os.rename(path + "/" + file, path + "/" + new_filename)
                    except FileExistsError as e:
                        pass
                    # Получаем новый путь
                    file_path = path + "/" + new_filename
                    # Если группа файла нам известна после классификации, то отправляем этот файл на сервер
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

        # Если очередной "файл" оказался директорией,
        # то переводим на транслит на латиницу её название и проверяем там все файлы
        # (транслит, поскольку pycurl не принимает utf-8, только ascii без кириллицы)
        else:
            new_path = translit(file_path, "ru", reversed=True)
            os.rename(file_path, new_path)
            check_files(new_path)


if __name__ == '__main__':
    # При запуске проекта, папка playground приводится в исходное состояние
    if DEBUG:
        os.system("xcopy playground_state playground /E /C /I /Y")
    else:
        os.system("cp -r playground_state/* playground/")
    # Получаем ответы классификации файлов тестовой директории и кэшируем для ускорения работы сервера
    check_files()
    # Если временной директории не существует, создаём
    if not os.path.exists("uploads"):
        os.mkdir("uploads")

    # Выбираем порт хоста сервера, в зависимости от конфигурации
    if DEBUG:
        app.run("0.0.0.0", 5000)
    else:
        app.run("0.0.0.0", 80)
