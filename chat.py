import flet as ft
import pathlib
import google.generativeai as genai
import google.ai.generativelanguage as glm
import cv2
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import PyPDF2
import numpy as np
import tempfile
import pandas as pd


genai.configure(api_key='AIzaSyA-4rqVHRtCdsLbeqmzzgvIUEYpabksKmc') 

pdfmetrics.registerFont(TTFont('TNR', 'C:/Windows/Fonts/TIMES.TTF'))

model_text = genai.GenerativeModel('gemini-1.5-pro-latest')
chat_text = model_text.start_chat(history=[])
model_vision = genai.GenerativeModel('gemini-1.5-flash-latest')
chat_vision = model_vision.start_chat(history=[])

new_message = None
last_response_text = None 
pdf_path = None


class Message():
    def __init__(self, user_name: str, text: str, message_type: str, is_image: bool = False):
        self.user_name = user_name
        self.text = text
        self.message_type = message_type
        self.is_image = is_image


class ChatMessage(ft.Row):
    def __init__(self, message: Message):
        super().__init__()
        self.vertical_alignment = "start"
        fixed_width = 500
        if message.is_image:
            self.controls = [
                ft.CircleAvatar(
                    content=ft.Text(self.get_initials(message.user_name)),
                    color=ft.colors.WHITE,
                    bgcolor=self.get_avatar_color(message.user_name),
                ),
                ft.Column(
                    [
                        ft.Text(message.user_name, weight="bold"),
                        ft.Image(message.text, width=fixed_width,
                                 height=fixed_width, fit="contain"),
                    ],
                    tight=True,
                    spacing=5,
                    width=fixed_width,
                ),
            ]
        else:
            self.controls = [
                ft.CircleAvatar(
                    content=ft.Text(self.get_initials(message.user_name)),
                    color=ft.colors.WHITE,
                    bgcolor=self.get_avatar_color(message.user_name),
                ),
                ft.Column(
                    [
                        ft.Text(message.user_name, weight="bold"),
                        ft.Text(message.text, selectable=True),
                    ],
                    tight=True,
                    spacing=5,
                    width=fixed_width,
                ),
            ]

    def get_initials(self, user_name: str):
        if user_name:
            return user_name[:1].capitalize()
        else:
            return "Unknown"

    def get_avatar_color(self, user_name: str):
        if user_name == "Me":
            return ft.colors.GREEN_800
        elif user_name == "DBR":
            return ft.colors.ORANGE
        else:
            return ft.colors.RED


image_path = None
processed_image_path = None
barcode_text = None
cap = None
camera_file_dialog = None
pdf_file_dialog = None
excel_file_dialog = None
excel_path = None
excel_data = None
current_chat = None
selected_color = None
calculate_button = None
pdf_options_button = None

chat_views = {
    "image_chat": ft.ListView(expand=True, spacing=10, auto_scroll=True),
    "pdf_chat": ft.ListView(expand=True, spacing=10, auto_scroll=True),
    "camera_chat": ft.ListView(expand=True, spacing=10, auto_scroll=True),
    "excel_chat": ft.ListView(expand=True, spacing=10, auto_scroll=True)
}

is_dark_mode = False


def main(page: ft.Page):
    global camera_file_dialog, image_path, pdf_file_dialog, excel_file_dialog
    global current_chat, is_dark_mode, processed_image_path, selected_color, calculate_button, pdf_options_button
    global new_message, pdf_path, last_response_text

    page.horizontal_alignment = "stretch"
    page.title = "AI CHAT"
    page.window_width = 800
    page.window_height = 600
    page.window_center()

    def update_theme():
        global is_dark_mode
        page.theme_mode = "dark" if is_dark_mode else "light"
        theme_icon_button.selected = is_dark_mode
        page.update()

    def change_theme(e):
        global is_dark_mode
        is_dark_mode = not is_dark_mode
        update_theme()

    def pick_files_result(e: ft.FilePickerResultEvent):
        global image_path, barcode_text, processed_image_path, selected_color, calculate_button
        barcode_text = None
        image_path = None
        processed_image_path = None
        if e.files is not None:
            image_path = e.files[0].path
            processed_image_path = process_image(
                image_path, selected_color)
            if processed_image_path is not None:
                page.pubsub.send_all(
                    Message("Me", processed_image_path, message_type="chat_message", is_image=True))
                if calculate_button:
                    calculate_button.visible = True

    def save_file_result(e: ft.FilePickerResultEvent):
        if e.path:
            save_last_response_to_pdf(e.path)

    def camera_file_result(e: ft.FilePickerResultEvent):
        if e.path:
            capture_image(e.path)

    def pick_pdf_result(e: ft.FilePickerResultEvent):
        global pdf_path, pdf_options_button
        if e.files is not None:
            pdf_path = e.files[0].path
            page.pubsub.send_all(
                Message("AI", "PDF yüklendi.", message_type="chat_message"))
            pdf_options_button.visible = True
        page.update()

    def pick_excel_result(e: ft.FilePickerResultEvent):
        global excel_path, excel_data
        excel_path = None
        excel_data = None
        if e.files is not None:
            excel_path = e.files[0].path
            try:
                excel_data = pd.read_excel(excel_path)
                page.pubsub.send_all(
                    Message("AI", "Dosya analiz ediliyor...", message_type="chat_message"))
                analyze_excel_data(excel_data)
            except Exception as err:
                page.pubsub.send_all(
                    Message("AI", f"Hata: {str(err)}", message_type="chat_message"))

    pick_files_dialog = ft.FilePicker(on_result=pick_files_result)
    save_file_dialog = ft.FilePicker(on_result=save_file_result)
    camera_file_dialog = ft.FilePicker(on_result=camera_file_result)
    pdf_file_dialog = ft.FilePicker(on_result=pick_pdf_result)
    excel_file_dialog = ft.FilePicker(on_result=pick_excel_result)

    page.overlay.append(pick_files_dialog)
    page.overlay.append(save_file_dialog)
    page.overlay.append(camera_file_dialog)
    page.overlay.append(pdf_file_dialog)
    page.overlay.append(excel_file_dialog)

    def pick_file(e):
        pick_files_dialog.pick_files()

    def clear_message(e):
        global image_path, processed_image_path, calculate_button, pdf_options_button
        image_path = None
        processed_image_path = None
        if calculate_button:
            calculate_button.visible = False
        if pdf_options_button:
            pdf_options_button.visible = False
        if current_chat:
            chat_views[current_chat].controls.clear()
        page.update()

    def send_message_click(e):
        global image_path, last_response_text, processed_image_path, selected_color
        if new_message.value != "" and current_chat:
            page.pubsub.send_all(
                Message("Me", new_message.value, message_type="chat_message"))

            question = new_message.value

            new_message.value = ""
            new_message.focus()
            page.update()

            if not question.startswith(":"):
                page.pubsub.send_all(
                    Message("AI", "Düşünüyorum...", message_type="chat_message"))

            if question == ":akademik":
                apply_image_prompt(
                    "Bu resim hakkında akademik bir makale yaz.")
            elif question == ":sanatsal":
                apply_image_prompt(
                    "Bu resim hakkında sanatsal bir makale yaz.")
            else:
                send_text_message(question)

    def send_text_message(question):
        global last_response_text 
        try:
            if processed_image_path:
                image_to_analyze = processed_image_path
            else:
                image_to_analyze = image_path
            if image_to_analyze is None:
                response = chat_text.send_message(question)
            else:
                try:
                    image_data = pathlib.Path(
                        image_to_analyze).read_bytes()
                except Exception as img_err:
                    page.pubsub.send_all(
                        Message("AI", f"Error reading image: {str(img_err)}", message_type="chat_message"))
                    return

                response = model_vision.generate_content(
                    glm.Content(
                        parts=[
                            glm.Part(
                                text=question),
                            glm.Part(
                                inline_data=glm.Blob(
                                    mime_type='image/jpeg',
                                    data=image_data
                                )
                            ),
                        ],
                    ))

            last_response_text = response.text 
            page.pubsub.send_all(
                Message("AI", last_response_text, message_type="chat_message"))
        except Exception as err:
            page.pubsub.send_all(
                Message("AI", f"Error: {str(err)}", message_type="chat_message"))

    def save_last_response_to_pdf(pdf_path):
        if last_response_text:
            c = canvas.Canvas(pdf_path, pagesize=letter)
            width, height = letter
            c.setFont('TNR', 12)

            text_y = height - 72
            lines = last_response_text.split('\n')
            for line in lines:
                for i in range(0, len(line), 100):
                    c.drawString(
                        36, text_y, line[i:i+100])
                    text_y -= 14
                    if text_y < 36:
                        c.showPage()
                        text_y = height - 72
            c.save()

    def save_pdf(e):
        save_file_dialog.save_file()

    def open_camera(e):
        global cap
        cap = cv2.VideoCapture(1)
        if not cap.isOpened():
            print("Cannot open camera")
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Can't receive frame (stream end?). Exiting ...")
                break
            cv2.imshow('frame', frame)
            if cv2.waitKey(1) & 0xFF == ord('x'):
                break

        cap.release()
        cv2.destroyAllWindows()

    def capture_image(path):
        global cap, image_path, processed_image_path, selected_color
        if cap and cap.isOpened():
            ret, frame = cap.read()
            if ret:
                cv2.imwrite(path, frame)
                image_path = path
                processed_image_path = process_image(
                    path, selected_color)
                page.pubsub.send_all(
                    Message("Me", processed_image_path, message_type="chat_message", is_image=True))
            else:
                print("Failed to capture image")

    def capture_image_button(e):
        camera_file_dialog.save_file()

    def on_message(message: Message):
        global current_chat, calculate_button, pdf_options_button
        if message.message_type == "chat_message" and current_chat:
            m = ChatMessage(message)
            chat_views[current_chat].controls.append(m)

            if message.user_name == "Me" and message.is_image and (current_chat == "image_chat" or current_chat == "camera_chat"):
                if calculate_button:
                    calculate_button.visible = True
            page.update()
        elif message.message_type == "login_message":
            m = ft.Text(message.text, italic=True,
                        color=ft.colors.BLACK45, size=12)
            page.update()

    def extract_text_from_pdf(pdf_path):
        with open(pdf_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            num_pages = len(pdf_reader.pages)
            text = ""
            for i in range(num_pages):
                page = pdf_reader.pages[i]
                text += page.extract_text()
            return text

    def pick_pdf(e):
        pdf_file_dialog.pick_files()

    def process_image(image_path, color=None):
        if color is None or color == "original":
            return image_path

        image = cv2.imread(image_path)
        if image is None:
            print(f"Görüntü yüklenemedi. Yol: {image_path}")
            return None

        hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        if color == "red":
            lower_color1 = np.array([0, 120, 70])
            upper_color1 = np.array([10, 255, 255])
            lower_color2 = np.array([170, 120, 70])
            upper_color2 = np.array([180, 255, 255])
            mask1 = cv2.inRange(hsv_image, lower_color1, upper_color1)
            mask2 = cv2.inRange(hsv_image, lower_color2, upper_color2)
            mask = mask1 + mask2
        elif color == "green":
            lower_color = np.array([40, 40, 40])
            upper_color = np.array([70, 255, 255])
            mask = cv2.inRange(hsv_image, lower_color, upper_color)
        elif color == "blue":
            lower_color = np.array([100, 150, 0])
            upper_color = np.array([140, 255, 255])
            mask = cv2.inRange(hsv_image, lower_color, upper_color)
        else:
            print(f"Geçersiz renk seçildi: {color}")
            return None

        color_detection = cv2.bitwise_and(image, image, mask=mask)
        processed_path = os.path.splitext(image_path)[
            0] + f"_{color}_processed.jpg"
        cv2.imwrite(processed_path, color_detection)
        return processed_path

    def choose_color(e):
        page.dialog = color_dialog
        color_dialog.open = True
        page.update()

    def color_selected(e):
        global selected_color, processed_image_path
        selected_color = e.control.data
        color_dialog.open = False

        apply_color_to_image()
        page.update()

    def apply_color_to_image():
        global processed_image_path
        if image_path:
            if selected_color == "original":
                processed_image_path = image_path
            else:
                processed_image_path = process_image(
                    image_path, selected_color)
            if processed_image_path is not None:
                page.pubsub.send_all(
                    Message("Me", processed_image_path, message_type="chat_message", is_image=True))

    color_dialog = ft.AlertDialog(
        title=ft.Text("Renk Seçin"),
        content=ft.Row(
            [
                ft.Container(
                    content=ft.ElevatedButton(
                        "Orijinal",
                        data="original",
                        on_click=color_selected,
                        width=100,
                        height=100
                    ),
                    padding=10
                ),
                ft.Container(
                    content=ft.ElevatedButton(
                        "Kırmızı",
                        bgcolor=ft.colors.RED,
                        data="red",
                        on_click=color_selected,
                        width=100,
                        height=100
                    ),
                    padding=10
                ),
                ft.Container(
                    content=ft.ElevatedButton(
                        "Yeşil",
                        bgcolor=ft.colors.GREEN,
                        data="green",
                        on_click=color_selected,
                        width=100,
                        height=100
                    ),
                    padding=10
                ),
                ft.Container(
                    content=ft.ElevatedButton(
                        "Mavi",
                        bgcolor=ft.colors.BLUE,
                        data="blue",
                        on_click=color_selected,
                        width=100,
                        height=100
                    ),
                    padding=10
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_AROUND
        ),
    )

    def calculate_exam_score(image_path):
        page.pubsub.send_all(
            Message("AI", "Düşünüyorum...", message_type="chat_message"))
        image = cv2.imread(image_path)
        if image is None:
            return "Görüntü yüklenemedi."

        hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower_red1 = np.array([0, 120, 70])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 120, 70])
        upper_red2 = np.array([180, 255, 255])
        mask1 = cv2.inRange(hsv_image, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv_image, lower_red2, upper_red2)
        mask = mask1 + mask2

        red_filtered_image = cv2.bitwise_and(image, image, mask=mask)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_image_path = temp_file.name
            cv2.imwrite(temp_image_path, red_filtered_image)

        try:
            with open(temp_image_path, "rb") as image_file:
                response = model_vision.generate_content(
                    glm.Content(
                        parts=[
                            glm.Part(
                                text="Bu resimdeki kırmızı renkteki sayıları bul ve topla."
                            ),
                            glm.Part(
                                inline_data=glm.Blob(
                                    mime_type='image/jpeg',
                                    data=image_file.read()
                                )
                            ),
                        ],
                    )
                )
            return response.text
        except Exception as e:
            return f"Hata: {e}"
        finally:
            os.remove(temp_image_path)

    def calculate_exam_score_from_image(e):
        global image_path
        if image_path:
            result = calculate_exam_score(image_path)
            page.pubsub.send_all(
                Message("AI", result, message_type="chat_message"))
        else:
            page.pubsub.send_all(
                Message("AI", "Lütfen önce bir resim seçin.", message_type="chat_message"))

    def apply_image_prompt(prompt):
        global image_path, processed_image_path, last_response_text 
        page.pubsub.send_all(
            Message("AI", "Düşünüyorum...", message_type="chat_message"))
        try:
            if processed_image_path:
                image_to_analyze = processed_image_path
            else:
                image_to_analyze = image_path

            with open(image_to_analyze, "rb") as image_file:
                response = model_vision.generate_content(
                    glm.Content(
                        parts=[
                            glm.Part(
                                text=prompt
                            ),
                            glm.Part(
                                inline_data=glm.Blob(
                                    mime_type='image/jpeg',
                                    data=image_file.read()
                                )
                            ),
                        ],
                    )
                )

            last_response_text = response.text 
            page.pubsub.send_all(
                Message("AI", last_response_text, message_type="chat_message"))
        except Exception as err:
            page.pubsub.send_all(
                Message("AI", f"Error: {str(err)}", message_type="chat_message"))

    def apply_prompt(prompt):
        global new_message
        new_message.value = prompt
        send_message_click(None)

    def pick_excel(e):
        excel_file_dialog.pick_files(
            allowed_extensions=["xlsx", "xls"]
        )

    def analyze_excel_data(excel_data):
        try:
            summary = excel_data.describe(include='all')

            question = f"İşte bir Excel dosyasından alınan verilerin özeti:\n\n{summary}\n\nBu veriler hakkında ne söyleyebilirsiniz? Verileri analiz et ve açıkla"

            response = chat_text.send_message(question)
            page.pubsub.send_all(
                Message("AI", response.text, message_type="chat_message"))
        except Exception as err:
            page.pubsub.send_all(
                Message("AI", f"Hata: {str(err)}", message_type="chat_message"))

    def handle_pdf_option(e):
        choice = e.control.text
        if choice == "Yorumla":
            apply_pdf_prompt("Bu PDF belgesini yorumla.")
        elif choice == "Özetle":
            apply_pdf_prompt("Bu PDF belgesini özetle.")
        elif choice == "Güncelleştir":
            apply_pdf_prompt(
                "Bu PDF belgesini güncelleştir.")
        elif choice == "PDF'i Ekrana Yaz":
            display_pdf_content()

    def apply_pdf_prompt(prompt):
        global pdf_path
        if pdf_path:
            pdf_text = extract_text_from_pdf(pdf_path)
            page.pubsub.send_all(
                Message("AI", "Düşünüyorum...", message_type="chat_message"))
            try:
                response = chat_text.send_message(
                    f"{prompt}\n\n{pdf_text}")
                page.pubsub.send_all(
                    Message("AI", response.text, message_type="chat_message"))
            except Exception as err:
                page.pubsub.send_all(
                    Message("AI", f"Error: {str(err)}", message_type="chat_message"))
        else:
            page.pubsub.send_all(
                Message("AI", "Lütfen önce bir PDF seçin.", message_type="chat_message"))

    def display_pdf_content():
        global pdf_path
        if pdf_path:
            pdf_text = extract_text_from_pdf(pdf_path)
            page.pubsub.send_all(
                Message("AI", pdf_text, message_type="chat_message"))
        else:
            page.pubsub.send_all(
                Message("AI", "Lütfen önce bir PDF seçin.", message_type="chat_message"))

    pdf_options_button = ft.PopupMenuButton(
        items=[
            ft.PopupMenuItem(text="Yorumla", on_click=handle_pdf_option),
            ft.PopupMenuItem(text="Özetle", on_click=handle_pdf_option),
            ft.PopupMenuItem(text="Güncelleştir", on_click=handle_pdf_option),
            ft.PopupMenuItem(text="PDF'i Ekrana Yaz",
                             on_click=handle_pdf_option)
        ],
        tooltip="PDF İşlemleri",
        icon=ft.icons.MORE_VERT,
        icon_color=ft.colors.BLACK,
        visible=False 
    )

    page.pubsub.subscribe(on_message)

    new_message = ft.TextField(
        hint_text="Write a message...",
        autofocus=True,
        shift_enter=True,
        min_lines=1,
        max_lines=5,
        filled=True,
        expand=True,
        on_submit=send_message_click,
    )

    def go_back_to_menu(e):
        global current_chat, selected_color, calculate_button, pdf_options_button
        current_chat = None
        selected_color = None
        if calculate_button:
            calculate_button.visible = False
        if pdf_options_button:
            pdf_options_button.visible = False
        page.clean()
        show_main_menu()

    def show_image_chat(e):
        global current_chat, selected_color, calculate_button
        current_chat = "image_chat"
        selected_color = None
        page.clean()

      
        calculate_button = ft.PopupMenuButton(
            items=[
                ft.PopupMenuItem(
                    text="Sınav Notu Hesapla", on_click=calculate_exam_score_from_image),
                ft.PopupMenuItem(text="Akademik Açıklama",
                                 on_click=lambda e: apply_image_prompt("Bu resme dair akademik bir deneme yaz.")),
                ft.PopupMenuItem(text="Sanatsal Açıklama",
                                 on_click=lambda e: apply_image_prompt("Bu resmi sanatsal bir bakış açısıyla yorumla."))
             
            ],
            tooltip="Resim İşlemleri",
            icon=ft.icons.MORE_VERT,
            icon_color=ft.colors.BLACK,
            visible=False  
        )

        page.add(
            ft.AppBar(title=ft.Text("Resim"),
                     leading=ft.IconButton(
                         icon=ft.icons.ARROW_BACK, on_click=go_back_to_menu)),
            ft.Container(
                content=chat_views["image_chat"],
                border=ft.border.all(1, ft.colors.OUTLINE),
                border_radius=5,
                padding=10,
                expand=True,
            ),
            ft.Row(
                [
                    ft.IconButton(
                        icon=ft.icons.UPLOAD_FILE,
                        tooltip="Resim Seç",
                        on_click=pick_file,

                    ),
                    detect_red_button,
                    ft.IconButton(
                        icon=ft.icons.DELETE_FOREVER_ROUNDED, icon_color=ft.colors.GREEN,
                        tooltip="Tüm Mesajları Temizle",
                        on_click=clear_message,
                    ),
                    calculate_button,
                    new_message,
                    ft.IconButton(
                        icon=ft.icons.SEND_ROUNDED,
                        tooltip="Mesaj Gönder",
                        on_click=send_message_click,


                    ),
                    ft.IconButton(
                        icon=ft.icons.DOWNLOAD,
                        tooltip="Son Cevabı PDF Olarak Kaydet",
                        on_click=save_pdf,
                    ),
                ]
            ),
        )

    def show_pdf_chat(e):
        global current_chat, selected_color, pdf_options_button
        current_chat = "pdf_chat"
        selected_color = None
        page.clean()
        page.add(
            ft.AppBar(title=ft.Text("PDF"),
                     leading=ft.IconButton(
                         icon=ft.icons.ARROW_BACK, on_click=go_back_to_menu)),
            ft.Container(
                content=chat_views["pdf_chat"],
                border=ft.border.all(1, ft.colors.OUTLINE),
                border_radius=5,
                padding=10,
                expand=True,
            ),
            ft.Row(
                [
                    ft.IconButton(
                        icon=ft.icons.PICTURE_AS_PDF,
                        tooltip="PDF Seç",
                        on_click=pick_pdf,
                        icon_color=ft.colors.RED,
                    ),
                    ft.IconButton(
                        icon=ft.icons.DELETE_FOREVER_ROUNDED, icon_color=ft.colors.GREEN,
                        tooltip="Tüm Mesajları Temizle",
                        on_click=clear_message,
                    ),
                    pdf_options_button,  
                    new_message,
                    ft.IconButton(
                        icon=ft.icons.SEND_ROUNDED,
                        tooltip="Mesaj Gönder",
                        on_click=send_message_click,
                    ),
                    ft.IconButton(
                        icon=ft.icons.DOWNLOAD,
                        tooltip="Son Cevabı PDF Olarak Kaydet",
                        on_click=save_pdf,
                    ),
                ]
            ),
        )

    def show_camera_chat(e):
        global current_chat, selected_color, calculate_button
        current_chat = "camera_chat"
        selected_color = None
        page.clean()

        if calculate_button is None:
           
            calculate_button = ft.PopupMenuButton(
                items=[
                    ft.PopupMenuItem(
                        text="Sınav Notu Hesapla", on_click=calculate_exam_score_from_image),
                    ft.PopupMenuItem(text="Akademik Açıklama",
                                     on_click=lambda e: apply_image_prompt("Bu resme dair akademik bir deneme yaz.")),
                    ft.PopupMenuItem(text="Sanatsal Açıklama",
                                     on_click=lambda e: apply_image_prompt("Bu resmi sanatsal bir bakış açısıyla yorumla."))
                   
                ],
                tooltip="Resim İşlemleri",
                icon=ft.icons.MORE_VERT,
                visible=False  
            )

        page.add(
            ft.AppBar(title=ft.Text("Kamera"),
                     leading=ft.IconButton(
                         icon=ft.icons.ARROW_BACK, on_click=go_back_to_menu)),
            ft.Container(
                content=chat_views["camera_chat"],
                border=ft.border.all(1, ft.colors.OUTLINE),
                border_radius=5,
                padding=10,
                expand=True,
            ),
            ft.Row(
                [
                    ft.IconButton(
                        icon=ft.icons.CAMERA_ALT, icon_color=ft.colors.BROWN_600,
                        tooltip="Kamerayı Aç",
                        on_click=open_camera,
                    ),
                    ft.IconButton(
                        icon=ft.icons.CAMERA, icon_color=ft.colors.PURPLE,
                        tooltip="Resim Çek",
                        on_click=capture_image_button,
                    ),
                    ft.IconButton(
                        icon=ft.icons.DELETE_FOREVER_ROUNDED, icon_color=ft.colors.GREEN,
                        tooltip="Tüm Mesajları Temizle",
                        on_click=clear_message,
                    ),
                    calculate_button,
                    new_message,
                    ft.IconButton(
                        icon=ft.icons.SEND_ROUNDED,
                        tooltip="Mesaj Gönder",
                        on_click=send_message_click,
                    ),
                    ft.IconButton(
                        icon=ft.icons.DOWNLOAD,
                        tooltip="PDF Olarak Kaydet",
                        on_click=save_pdf,
                    ),
                ]
            ),
        )

    def show_excel_chat(e):
        global current_chat
        current_chat = "excel_chat"
        page.clean()
        page.add(
            ft.AppBar(title=ft.Text("Excel"),
                     leading=ft.IconButton(
                         icon=ft.icons.ARROW_BACK, on_click=go_back_to_menu)),
            ft.Container(
                content=chat_views["excel_chat"],
                border=ft.border.all(1, ft.colors.OUTLINE),
                border_radius=5,
                padding=10,
                expand=True,
            ),
            ft.Row(
                [
                    ft.IconButton(
                        icon=ft.icons.UPLOAD_FILE,
                        tooltip="Excel Dosyası Seç",
                        on_click=pick_excel,
                    ),
                    ft.IconButton(
                        icon=ft.icons.DELETE_FOREVER_ROUNDED, icon_color=ft.colors.GREEN,
                        tooltip="Tüm Mesajları Temizle",
                        on_click=clear_message,
                    ),
                    new_message,
                    ft.IconButton(
                        icon=ft.icons.SEND_ROUNDED,
                        tooltip="Mesaj Gönder",
                        on_click=send_message_click,
                    ),
                    ft.IconButton(
                        icon=ft.icons.DOWNLOAD,
                        tooltip="Son Cevabı PDF Olarak Kaydet",
                        on_click=save_pdf,
                    ),
                ]
            ),
        )

    theme_icon_button = ft.IconButton(
        icon=ft.icons.BRIGHTNESS_4,
        selected_icon=ft.icons.BRIGHTNESS_7,
        tooltip="Temayı Değiştir",
        on_click=change_theme,
    )

    detect_red_button = ft.IconButton(
        icon=ft.icons.COLORIZE,
        tooltip="Renk Seç",
        selected=False,
        icon_color=ft.colors.RED,
        on_click=choose_color,
    )

    main_menu_buttons = ft.Column(
        [
            ft.ElevatedButton("Resim", on_click=show_image_chat,
                             icon=ft.icons.IMAGE, color=ft.colors.BLUE),
            ft.ElevatedButton("PDF", on_click=show_pdf_chat,
                             icon=ft.icons.UPLOAD_FILE, color=ft.colors.RED),
            ft.ElevatedButton("Kamera", on_click=show_camera_chat,
                             icon=ft.icons.CAMERA_ALT, color=ft.colors.GREEN),
            ft.ElevatedButton("Excel", on_click=show_excel_chat,
                             icon=ft.icons.FILE_COPY, color=ft.colors.ORANGE),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
    )

    def show_main_menu():
        page.add(
            ft.Container(
                content=main_menu_buttons,
                expand=True,
                alignment=ft.alignment.center,
            ),
            ft.AppBar(title=ft.Text("AI Chat"),
                     actions=[theme_icon_button],
                     )
        )

    show_main_menu()
    update_theme()


ft.app(main)