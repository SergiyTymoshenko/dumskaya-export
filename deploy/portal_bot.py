#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Кабинет заказчика и подрядчика в боте студии (часть класса Bot) и переписка студии с заказчиками.

  • Ссылка-приглашение t.me/<бот>?start=pj_… (её даёт «Студия»): человек нажимает «Старт» — его Telegram привязан
    к заказчику или подрядчику проекта, слева от поля ввода появляется кнопка «Мой проект» (на его языке).
  • Переписка: заказчик пишет в кабинете или прямо в чат бота — Ирине приходит сообщение с переводом на русский
    (если написано не по-русски и не по-украински); Ирина отвечает свайпом по этому сообщению или в «Студии» — заказчикам
    уходит её ответ с переводом на их язык. Фото и документы — тоже. Подрядчики в переписке не участвуют.
  • Суммы работ подрядчиков: внесла студия или сам подрядчик — заказчику приходит «Подтверждаю / Не согласен».
  • Товары и доп. услуги: заказчику — сообщение о новом товаре, услуге, доставке (если в «Студии» отмечено «Сообщить»).
  • Напоминания об оплате доп. услуг (помесячно и разовых): заказчику и Ирине — в день оплаты и через 7 дней, если
    не оплачено (днём, 10:00–20:00 по Братиславе).
Тексты для заказчиков и подрядчиков — на пяти языках (RU, UA, EN, SK, DE) по языку их Telegram или выбранному в кабинете.
Только стандартная библиотека Python 3."""
import html
import json
import threading
import time
from datetime import date, datetime, timezone

from crm import TZ, CrmError
from crm_portal import STUDIO, ui_lang

try:
    from translate import lang_from, provider as translate_provider, translate_text
except ImportError:                    # pragma: no cover
    def translate_provider():
        return None

    def translate_text(text, target):
        return None

    def lang_from(code):
        return ""

PORTAL_ROLES = ("client", "crew")
CHAT_FILE_MAX = 20 * 1024 * 1024       # больше Telegram боту скачать не даёт
CHAT_MAP_DAYS = 180                    # ответ свайпом работает на сообщения не старше полугода

T = {
    "menu": {"ru": "Мой проект", "uk": "Мій проєкт", "en": "My project", "sk": "Môj projekt", "de": "Mein Projekt"},
    "open": {"ru": "📁 Открыть проект", "uk": "📁 Відкрити проєкт", "en": "📁 Open project", "sk": "📁 Otvoriť projekt",
             "de": "📁 Projekt öffnen"},
    "open_chat": {"ru": "💬 Открыть переписку", "uk": "💬 Відкрити листування", "en": "💬 Open chat", "sk": "💬 Otvoriť konverzáciu",
                  "de": "💬 Chat öffnen"},
    "welcome_client": {
        "ru": "Здравствуйте, {name}! Это кабинет вашего проекта «{project}» в студии DUMSKAYA DESIGN: оплаты и что осталось "
              "оплатить, доп. услуги и товары, документы и визуализации, контакты подрядчиков и переписка с Ириной.\n\n"
              "Открыть кабинет — кнопка «{menu}» слева от поля ввода. Написать Ирине можно прямо сюда, в чат.",
        "uk": "Добрий день, {name}! Це кабінет вашого проєкту «{project}» у студії DUMSKAYA DESIGN: оплати і що залишилося "
              "сплатити, додаткові послуги й товари, документи й візуалізації, контакти підрядників і листування з Іриною.\n\n"
              "Відкрити кабінет — кнопка «{menu}» ліворуч від поля введення. Написати Ірині можна просто сюди, в чат.",
        "en": "Hello {name}! This is the app for your project “{project}” with DUMSKAYA DESIGN: payments and what is left to pay, "
              "extra services and furniture orders, documents and renderings, contractors’ contacts and your chat with Irina.\n\n"
              "To open it, tap “{menu}” next to the message field. You can also write to Irina right here in this chat.",
        "sk": "Dobrý deň, {name}! Toto je aplikácia vášho projektu „{project}“ v štúdiu DUMSKAYA DESIGN: platby a čo ešte "
              "zostáva zaplatiť, doplnkové služby a objednaný tovar, dokumenty a vizualizácie, kontakty na remeselníkov "
              "a konverzácia s Irinou.\n\nOtvoríte ju tlačidlom „{menu}“ vedľa poľa na písanie. Irine môžete napísať aj priamo sem do chatu.",
        "de": "Guten Tag, {name}! Das ist die App zu Ihrem Projekt „{project}“ bei DUMSKAYA DESIGN: Zahlungen und offene Beträge, "
              "Zusatzleistungen und bestellte Möbel, Unterlagen und Visualisierungen, Kontakte der Handwerker und der Chat mit Irina.\n\n"
              "Öffnen Sie sie über „{menu}“ neben dem Eingabefeld. Sie können Irina auch direkt hier im Chat schreiben."},
    "welcome_crew": {
        "ru": "Здравствуйте, {name}! Это кабинет подрядчика студии DUMSKAYA DESIGN по проекту «{project}»: обмерный план, "
              "визуализации и документация, контакты заказчика и ваши расчёты со студией. Сумму работ можно внести самому — "
              "заказчик её подтвердит.\n\nОткрыть кабинет — кнопка «{menu}» слева от поля ввода.",
        "uk": "Добрий день, {name}! Це кабінет підрядника студії DUMSKAYA DESIGN за проєктом «{project}»: обмірний план, "
              "візуалізації й документація, контакти замовника і ваші розрахунки зі студією. Суму робіт можна внести самому — "
              "замовник її підтвердить.\n\nВідкрити кабінет — кнопка «{menu}» ліворуч від поля введення.",
        "en": "Hello {name}! This is the contractor app of DUMSKAYA DESIGN for the project “{project}”: measured plan, renderings "
              "and documentation, the client’s contacts and your account with the studio. You can enter the price of your work "
              "yourself — the client will confirm it.\n\nTo open it, tap “{menu}” next to the message field.",
        "sk": "Dobrý deň, {name}! Toto je aplikácia pre dodávateľov štúdia DUMSKAYA DESIGN k projektu „{project}“: zameranie, "
              "vizualizácie a dokumentácia, kontakty na klienta a vaše vyúčtovanie so štúdiom. Cenu prác môžete zadať aj sami — "
              "klient ju potvrdí.\n\nOtvoríte ju tlačidlom „{menu}“ vedľa poľa na písanie.",
        "de": "Guten Tag, {name}! Das ist die Handwerker-App von DUMSKAYA DESIGN zum Projekt „{project}“: Aufmaß, Visualisierungen "
              "und Unterlagen, Kontakte des Kunden und Ihre Abrechnung mit dem Studio. Den Preis Ihrer Arbeiten können Sie selbst "
              "eintragen — der Kunde bestätigt ihn.\n\nÖffnen Sie sie über „{menu}“ neben dem Eingabefeld."},
    "invite_bad": {
        "ru": "Ссылка недействительна: она уже использована или устарела. Попросите у студии DUMSKAYA DESIGN новую.",
        "uk": "Посилання недійсне: його вже використано або воно застаріло. Попросіть у студії DUMSKAYA DESIGN нове.",
        "en": "This link is no longer valid: it has been used or has expired. Please ask DUMSKAYA DESIGN for a new one.",
        "sk": "Tento odkaz už neplatí: bol použitý alebo vypršal. Požiadajte štúdio DUMSKAYA DESIGN o nový.",
        "de": "Dieser Link ist nicht mehr gültig: Er wurde bereits verwendet oder ist abgelaufen. Bitte fragen Sie DUMSKAYA DESIGN nach einem neuen."},
    "auto_tr": {"ru": "Переведено автоматически. Оригинал — в кабинете.", "uk": "Перекладено автоматично. Оригінал — у кабінеті.",
                "en": "Translated automatically. The original is in the project app.",
                "sk": "Preložené automaticky. Originál nájdete v aplikácii projektu.",
                "de": "Automatisch übersetzt. Das Original finden Sie in der Projekt-App."},
    "sent": {"ru": "✓ Отправлено в переписку проекта «{project}».", "uk": "✓ Надіслано в листування проєкту «{project}».",
             "en": "✓ Sent to the chat of “{project}”.", "sk": "✓ Odoslané do konverzácie projektu „{project}“.",
             "de": "✓ Im Chat zu „{project}“ gesendet."},
    "pick": {"ru": "К какому проекту это сообщение?", "uk": "До якого проєкту це повідомлення?", "en": "Which project is this message about?",
             "sk": "Ku ktorému projektu je táto správa?", "de": "Zu welchem Projekt gehört diese Nachricht?"},
    "too_big": {"ru": "Файл больше 20 МБ — Telegram не даёт боту его скачать. Пришлите его Ирине другим способом.",
                "uk": "Файл більший за 20 МБ — Telegram не дає боту його завантажити. Надішліть його Ірині іншим способом.",
                "en": "The file is larger than 20 MB — Telegram doesn’t let the bot download it. Please send it to Irina another way.",
                "sk": "Súbor má viac ako 20 MB — Telegram ho botovi nedovolí stiahnuť. Pošlite ho Irine inak.",
                "de": "Die Datei ist größer als 20 MB — Telegram lässt den Bot sie nicht herunterladen. Bitte senden Sie sie Irina auf anderem Weg."},
    "crew_no_chat": {
        "ru": "Сообщения отсюда студии не передаются. Связаться со студией: {phone}, {email}.",
        "uk": "Повідомлення звідси студії не передаються. Зв’язатися зі студією: {phone}, {email}.",
        "en": "Messages from here are not passed on to the studio. To contact the studio: {phone}, {email}.",
        "sk": "Správy odtiaľto sa štúdiu neodovzdávajú. Kontakt na štúdio: {phone}, {email}.",
        "de": "Nachrichten von hier werden nicht an das Studio weitergeleitet. Kontakt zum Studio: {phone}, {email}."},
    "no_projects": {"ru": "В кабинете пока нет проектов.", "uk": "У кабінеті поки немає проєктів.", "en": "There are no projects in your app yet.",
                    "sk": "V aplikácii zatiaľ nie sú žiadne projekty.", "de": "In Ihrer App gibt es noch keine Projekte."},
    "stage_ask": {
        "ru": "🧾 <b>Сумма работ на подтверждение</b> · «{project}»\n{who}: {title} — <b>{amount}</b>\n\nЕсли сумма верная — нажмите «Подтверждаю».",
        "uk": "🧾 <b>Сума робіт на підтвердження</b> · «{project}»\n{who}: {title} — <b>{amount}</b>\n\nЯкщо сума правильна — натисніть «Підтверджую».",
        "en": "🧾 <b>Please confirm the price of the work</b> · “{project}”\n{who}: {title} — <b>{amount}</b>\n\nIf the amount is correct, tap “I confirm”.",
        "sk": "🧾 <b>Potvrďte cenu prác</b> · „{project}“\n{who}: {title} — <b>{amount}</b>\n\nAk je suma správna, ťuknite na „Potvrdzujem“.",
        "de": "🧾 <b>Bitte bestätigen Sie den Preis der Arbeiten</b> · „{project}“\n{who}: {title} — <b>{amount}</b>\n\nWenn der Betrag stimmt, tippen Sie auf „Ich bestätige“."},
    "btn_confirm": {"ru": "✓ Подтверждаю", "uk": "✓ Підтверджую", "en": "✓ I confirm", "sk": "✓ Potvrdzujem", "de": "✓ Ich bestätige"},
    "btn_dispute": {"ru": "Не согласен", "uk": "Не згоден", "en": "I disagree", "sk": "Nesúhlasím", "de": "Stimmt nicht"},
    "you_confirmed": {"ru": "✓ Вы подтвердили сумму.", "uk": "✓ Ви підтвердили суму.", "en": "✓ You have confirmed the amount.",
                      "sk": "✓ Sumu ste potvrdili.", "de": "✓ Sie haben den Betrag bestätigt."},
    "you_disputed": {"ru": "Отмечено: вы не согласны с суммой. Напишите Ирине, что не так, — прямо сюда, в чат.",
                     "uk": "Позначено: ви не згодні із сумою. Напишіть Ірині, що не так, — просто сюди, в чат.",
                     "en": "Noted: you disagree with the amount. Please tell Irina what is wrong — right here in this chat.",
                     "sk": "Zaznamenané: so sumou nesúhlasíte. Napíšte Irine, čo nie je v poriadku — priamo sem do chatu.",
                     "de": "Vermerkt: Sie sind mit dem Betrag nicht einverstanden. Schreiben Sie Irina bitte hier im Chat, was nicht stimmt."},
    "stage_gone": {"ru": "Эта сумма уже изменилась — посмотрите в кабинете.", "uk": "Ця сума вже змінилася — подивіться в кабінеті.",
                   "en": "This amount has changed — please check the project app.", "sk": "Táto suma sa medzitým zmenila — pozrite si aplikáciu projektu.",
                   "de": "Dieser Betrag hat sich geändert — bitte sehen Sie in der Projekt-App nach."},
    "c_confirmed": {"ru": "✓ Заказчик подтвердил сумму · «{project}»\n{title} — <b>{amount}</b>",
                    "uk": "✓ Замовник підтвердив суму · «{project}»\n{title} — <b>{amount}</b>",
                    "en": "✓ The client has confirmed the amount · “{project}”\n{title} — <b>{amount}</b>",
                    "sk": "✓ Klient potvrdil sumu · „{project}“\n{title} — <b>{amount}</b>",
                    "de": "✓ Der Kunde hat den Betrag bestätigt · „{project}“\n{title} — <b>{amount}</b>"},
    "c_disputed": {"ru": "⚠️ Заказчик не согласен с суммой · «{project}»\n{title} — <b>{amount}</b>\nСтудия уточнит и свяжется с вами.",
                   "uk": "⚠️ Замовник не згоден із сумою · «{project}»\n{title} — <b>{amount}</b>\nСтудія уточнить і зв’яжеться з вами.",
                   "en": "⚠️ The client disagrees with the amount · “{project}”\n{title} — <b>{amount}</b>\nThe studio will clarify and get back to you.",
                   "sk": "⚠️ Klient nesúhlasí so sumou · „{project}“\n{title} — <b>{amount}</b>\nŠtúdio to preverí a ozve sa vám.",
                   "de": "⚠️ Der Kunde ist mit dem Betrag nicht einverstanden · „{project}“\n{title} — <b>{amount}</b>\nDas Studio klärt das und meldet sich bei Ihnen."},
    "c_by_studio": {"ru": "🧾 Студия внесла сумму ваших работ · «{project}»\n{title} — <b>{amount}</b>",
                    "uk": "🧾 Студія внесла суму ваших робіт · «{project}»\n{title} — <b>{amount}</b>",
                    "en": "🧾 The studio has entered the price of your work · “{project}”\n{title} — <b>{amount}</b>",
                    "sk": "🧾 Štúdio zadalo cenu vašich prác · „{project}“\n{title} — <b>{amount}</b>",
                    "de": "🧾 Das Studio hat den Preis Ihrer Arbeiten eingetragen · „{project}“\n{title} — <b>{amount}</b>"},
    "link_new": {"ru": "📁 Вас добавили в проект «{project}»{trade}. Документация и контакты заказчика — в кабинете.",
                 "uk": "📁 Вас додали до проєкту «{project}»{trade}. Документація й контакти замовника — у кабінеті.",
                 "en": "📁 You have been added to the project “{project}”{trade}. Documents and the client’s contacts are in the app.",
                 "sk": "📁 Pridali vás do projektu „{project}“{trade}. Dokumentácia a kontakty na klienta sú v aplikácii.",
                 "de": "📁 Sie wurden zum Projekt „{project}“{trade} hinzugefügt. Unterlagen und Kontakte des Kunden finden Sie in der App."},
    "order_new": {"ru": "🛋 <b>Новый товар в проекте</b> «{project}»\n{title} — <b>{amount}</b>{planned}",
                  "uk": "🛋 <b>Новий товар у проєкті</b> «{project}»\n{title} — <b>{amount}</b>{planned}",
                  "en": "🛋 <b>New item in your project</b> “{project}”\n{title} — <b>{amount}</b>{planned}",
                  "sk": "🛋 <b>Nový tovar v projekte</b> „{project}“\n{title} — <b>{amount}</b>{planned}",
                  "de": "🛋 <b>Neuer Artikel in Ihrem Projekt</b> „{project}“\n{title} — <b>{amount}</b>{planned}"},
    "planned": {"ru": "\nПлановая поставка: {date}", "uk": "\nПланова поставка: {date}", "en": "\nPlanned delivery: {date}",
                "sk": "\nPlánované dodanie: {date}", "de": "\nGeplante Lieferung: {date}"},
    "order_delivered": {"ru": "🚚 <b>Товар доставлен</b> · «{project}»\n{title}{rest}", "uk": "🚚 <b>Товар доставлено</b> · «{project}»\n{title}{rest}",
                        "en": "🚚 <b>Delivered</b> · “{project}”\n{title}{rest}", "sk": "🚚 <b>Tovar je dodaný</b> · „{project}“\n{title}{rest}",
                        "de": "🚚 <b>Geliefert</b> · „{project}“\n{title}{rest}"},
    "rest": {"ru": "\nОсталось доплатить: <b>{amount}</b>", "uk": "\nЗалишилося доплатити: <b>{amount}</b>", "en": "\nLeft to pay: <b>{amount}</b>",
             "sk": "\nZostáva doplatiť: <b>{amount}</b>", "de": "\nNoch zu zahlen: <b>{amount}</b>"},
    "paid_full": {"ru": "\nОплачено полностью — спасибо!", "uk": "\nСплачено повністю — дякуємо!", "en": "\nPaid in full — thank you!",
                  "sk": "\nZaplatené v plnej výške — ďakujeme!", "de": "\nVollständig bezahlt — vielen Dank!"},
    "service_new": {"ru": "🧾 <b>Новая услуга</b> · «{project}»\n{title} — <b>{amount}</b>{per}\n{when}",
                    "uk": "🧾 <b>Нова послуга</b> · «{project}»\n{title} — <b>{amount}</b>{per}\n{when}",
                    "en": "🧾 <b>New service</b> · “{project}”\n{title} — <b>{amount}</b>{per}\n{when}",
                    "sk": "🧾 <b>Nová služba</b> · „{project}“\n{title} — <b>{amount}</b>{per}\n{when}",
                    "de": "🧾 <b>Neue Leistung</b> · „{project}“\n{title} — <b>{amount}</b>{per}\n{when}"},
    "per_month": {"ru": " в месяц", "uk": " на місяць", "en": " per month", "sk": " mesačne", "de": " pro Monat"},
    "pay_by": {"ru": "Оплата до {date}", "uk": "Оплата до {date}", "en": "Payment due by {date}", "sk": "Splatnosť do {date}", "de": "Zahlbar bis {date}"},
    "first_pay": {"ru": "Первый платёж: {date}", "uk": "Перший платіж: {date}", "en": "First payment: {date}", "sk": "Prvá platba: {date}",
                  "de": "Erste Zahlung: {date}"},
    "remind_due": {
        "ru": "🔔 <b>Напоминание об оплате</b> · «{project}»\n{title}: <b>{amount}</b> — срок {date}.\n\nЕсли вы уже оплатили — спасибо, это сообщение можно не читать.",
        "uk": "🔔 <b>Нагадування про оплату</b> · «{project}»\n{title}: <b>{amount}</b> — термін {date}.\n\nЯкщо ви вже сплатили — дякуємо, це повідомлення можна не читати.",
        "en": "🔔 <b>Payment reminder</b> · “{project}”\n{title}: <b>{amount}</b> — due {date}.\n\nIf you have already paid, thank you — please ignore this message.",
        "sk": "🔔 <b>Pripomienka platby</b> · „{project}“\n{title}: <b>{amount}</b> — splatnosť {date}.\n\nAk ste už zaplatili, ďakujeme — túto správu môžete ignorovať.",
        "de": "🔔 <b>Zahlungserinnerung</b> · „{project}“\n{title}: <b>{amount}</b> — fällig am {date}.\n\nFalls Sie bereits bezahlt haben, vielen Dank — dann können Sie diese Nachricht ignorieren."},
    "remind_overdue": {
        "ru": "🔔 <b>Оплата пока не поступила</b> · «{project}»\n{title}: <b>{amount}</b>, срок был {date}.\n\nЕсли вы уже оплатили — напишите Ирине, мы проверим.",
        "uk": "🔔 <b>Оплата поки не надійшла</b> · «{project}»\n{title}: <b>{amount}</b>, термін був {date}.\n\nЯкщо ви вже сплатили — напишіть Ірині, ми перевіримо.",
        "en": "🔔 <b>Payment not received yet</b> · “{project}”\n{title}: <b>{amount}</b>, it was due {date}.\n\nIf you have already paid, please tell Irina and we will check.",
        "sk": "🔔 <b>Platba zatiaľ neprišla</b> · „{project}“\n{title}: <b>{amount}</b>, splatnosť bola {date}.\n\nAk ste už zaplatili, napíšte Irine, preveríme to.",
        "de": "🔔 <b>Zahlung noch nicht eingegangen</b> · „{project}“\n{title}: <b>{amount}</b>, fällig war sie am {date}.\n\nFalls Sie bereits bezahlt haben, schreiben Sie bitte Irina — wir prüfen das."},
    "closed": {"ru": "Доступ к кабинету проекта закрыт. Если это ошибка — свяжитесь со студией DUMSKAYA DESIGN.",
               "uk": "Доступ до кабінету проєкту закрито. Якщо це помилка — зв’яжіться зі студією DUMSKAYA DESIGN.",
               "en": "Access to the project app has been closed. If this is a mistake, please contact DUMSKAYA DESIGN.",
               "sk": "Prístup do aplikácie projektu bol zrušený. Ak ide o omyl, kontaktujte štúdio DUMSKAYA DESIGN.",
               "de": "Der Zugang zur Projekt-App wurde beendet. Falls das ein Irrtum ist, wenden Sie sich bitte an DUMSKAYA DESIGN."},
    "invite_client": {
        "ru": "Здравствуйте, {name}! Это ссылка на кабинет вашего проекта «{project}» в студии DUMSKAYA DESIGN: оплаты, документы "
              "и визуализации, контакты подрядчиков и переписка с Ириной. Откройте её в Telegram и нажмите кнопку внизу экрана («Старт»):\n"
              "{link}\n\nСсылка личная, для одного человека, и действует 14 дней.",
        "uk": "Добрий день, {name}! Це посилання на кабінет вашого проєкту «{project}» у студії DUMSKAYA DESIGN: оплати, документи "
              "й візуалізації, контакти підрядників і листування з Іриною. Відкрийте його в Telegram і натисніть кнопку внизу екрана («Почати»):\n"
              "{link}\n\nПосилання особисте, для однієї людини, і діє 14 днів.",
        "en": "Hello {name}! Here is the link to the app for your project “{project}” with DUMSKAYA DESIGN: payments, documents "
              "and renderings, contractors’ contacts and your chat with Irina. Open it in Telegram and tap the button at the bottom (“Start”):\n"
              "{link}\n\nThe link is personal, for one person, and is valid for 14 days.",
        "sk": "Dobrý deň, {name}! Posielame odkaz na aplikáciu vášho projektu „{project}“ v štúdiu DUMSKAYA DESIGN: platby, dokumenty "
              "a vizualizácie, kontakty na remeselníkov a konverzácia s Irinou. Otvorte ho v Telegrame a ťuknite na tlačidlo dole („Štart“):\n"
              "{link}\n\nOdkaz je osobný, pre jednu osobu, a platí 14 dní.",
        "de": "Guten Tag, {name}! Hier ist der Link zur App Ihres Projekts „{project}“ bei DUMSKAYA DESIGN: Zahlungen, Unterlagen "
              "und Visualisierungen, Kontakte der Handwerker und der Chat mit Irina. Öffnen Sie ihn in Telegram und tippen Sie unten auf die Schaltfläche („Starten“):\n"
              "{link}\n\nDer Link ist persönlich, für eine Person, und 14 Tage gültig."},
    "invite_contractor": {
        "ru": "Здравствуйте, {name}! Это ссылка на кабинет подрядчика по проекту «{project}» студии DUMSKAYA DESIGN: обмерный план, "
              "визуализации и документация, контакты заказчика и расчёты со студией. Откройте её в Telegram и нажмите кнопку внизу экрана («Старт»):\n"
              "{link}\n\nСсылка личная, для одного человека, и действует 14 дней.",
        "uk": "Добрий день, {name}! Це посилання на кабінет підрядника за проєктом «{project}» студії DUMSKAYA DESIGN: обмірний план, "
              "візуалізації й документація, контакти замовника і розрахунки зі студією. Відкрийте його в Telegram і натисніть кнопку внизу екрана («Почати»):\n"
              "{link}\n\nПосилання особисте, для однієї людини, і діє 14 днів.",
        "en": "Hello {name}! Here is the link to the contractor app of DUMSKAYA DESIGN for the project “{project}”: measured plan, "
              "renderings and documentation, the client’s contacts and your account with the studio. Open it in Telegram and tap the button at the bottom (“Start”):\n"
              "{link}\n\nThe link is personal, for one person, and is valid for 14 days.",
        "sk": "Dobrý deň, {name}! Posielame odkaz na aplikáciu pre dodávateľov štúdia DUMSKAYA DESIGN k projektu „{project}“: zameranie, "
              "vizualizácie a dokumentácia, kontakty na klienta a vyúčtovanie so štúdiom. Otvorte ho v Telegrame a ťuknite na tlačidlo dole („Štart“):\n"
              "{link}\n\nOdkaz je osobný, pre jednu osobu, a platí 14 dní.",
        "de": "Guten Tag, {name}! Hier ist der Link zur Handwerker-App von DUMSKAYA DESIGN für das Projekt „{project}“: Aufmaß, "
              "Visualisierungen und Unterlagen, Kontakte des Kunden und die Abrechnung mit dem Studio. Öffnen Sie ihn in Telegram und tippen Sie unten auf die Schaltfläche („Starten“):\n"
              "{link}\n\nDer Link ist persönlich, für eine Person, und 14 Tage gültig."},
}
SYM = {"EUR": "€", "USD": "$", "UAH": "₴", "PLN": "zł", "CZK": "Kč", "GBP": "£", "CHF": "CHF"}


def t(lang, key, **kw):
    d = T[key]
    s = d.get(lang) or d["en"]
    return s.format(**kw) if kw else s


def esc(s):
    return html.escape(str(s or ""), quote=False)


def money(x, cur="EUR", lang="ru"):
    """12 000 € / 12,000 € (по-английски) / 1 500,50 ₴."""
    x = round(float(x or 0), 2)
    whole, frac = f"{abs(x):,.2f}".split(".")
    sep, dec = (",", ".") if lang == "en" else (" ", ",")
    s = whole.replace(",", sep) + (dec + frac if frac != "00" else "")
    return ("−" if x < 0 else "") + s + " " + SYM.get(cur, cur)


def dmy(s):
    try:
        return date.fromisoformat(str(s)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(s or "")


class PortalBotMixin:
    # ---------- язык и кнопки ----------
    def lang_of(self, uid):
        """Язык кабинета: выбранный в кабинете, иначе язык Telegram (ru, uk, en, sk, de; остальным — английский)."""
        return ui_lang(self.s.get(f"ui:lang:{uid}") or self.s.get(f"tg:lang:{uid}") or "en")

    @staticmethod
    def can_translate():
        return bool(translate_provider())

    def portal_url(self):
        url = self.stats_app_url()
        return url.replace("/api/stats/app", "/api/portal/app") if url else None

    def portal_row(self, lang, query="", key="open"):
        url = self.portal_url()
        return [(t(lang, key), {"web_app": {"url": url + (f"?{query}" if query else "")}})] if url else None

    def fill_labels(self, texts, lang):
        """Перевести названия для кабинета (в фоне) и запомнить."""
        for x in texts[:60]:
            self.loc(x, lang)

    def loc(self, text, lang):
        """Название (услуги, товара, этапа, проекта) на языке человека: из словаря или сохранённого перевода,
        иначе — перевести сейчас и запомнить; не получилось — как есть."""
        x = self.portal.label(text, lang)
        if x is not None:
            return x
        if not self.can_translate():
            return text
        try:
            r = translate_text(text, lang)
        except Exception as e:  # noqa: BLE001
            self.log(f"перевод названия ({lang}): ошибка {type(e).__name__}: {e}")
            return text
        self.portal.remember_label(text, lang, r[1] if r else text)
        return r[1] if r else text

    def designer_name(self, lang):
        return STUDIO["designer"].get(lang) or STUDIO["designer_latin"]

    def sync_portal_menu(self, uid):
        """Кнопка «Мой проект» слева от поля ввода — у тех, у кого есть проекты в кабинете (у студии — своя кнопка «Студия»)."""
        u = self.user(uid)
        if not u or self.is_admin(u) or not getattr(self, "portal", None):
            return
        url = self.portal_url()
        if u["status"] == "active" and url and self.portal.projects_for(uid):
            self.api("setChatMenuButton", chat_id=uid, menu_button={"type": "web_app", "text": t(self.lang_of(uid), "menu"),
                                                                     "web_app": {"url": url}})
            self.s.put(f"pmenu:{uid}", "1")
        elif self.s.get(f"pmenu:{uid}"):
            self.api("setChatMenuButton", chat_id=uid, menu_button={"type": "commands"})
            self.s.drop(f"pmenu:{uid}")

    def portal_welcome(self, u):
        lang = self.lang_of(u["tg_id"])
        ps = self.portal.projects_for(u["tg_id"]) if getattr(self, "portal", None) else []
        if not ps:
            return t(lang, "no_projects")
        p = ps[0]
        key = "welcome_client" if "client" in p["roles"] else "welcome_crew"
        title = ", ".join(self.loc(x["title"], lang) for x in ps[:3])
        return t(lang, key, name=esc(u["name"] or ""), project=esc(title), menu=t(lang, "menu"))

    def invite_text(self, lang, kind, name, project, link):
        return t(ui_lang(lang), "invite_client" if kind == "client" else "invite_contractor", name=name, project=project, link=link)

    # ---------- вход по ссылке-приглашению ----------
    def join_portal(self, uid, name, username, lang_code, u, token):
        if lang_code and not self.s.get(f"tg:lang:{uid}"):
            self.s.put(f"tg:lang:{uid}", str(lang_code)[:8])
        if u and u["status"] == "active" and self.is_admin(u):
            return self.send(uid, "Это ссылка для заказчика или подрядчика — по ней он попадёт в кабинет проекта. "
                                  "Вы в студии: кабинет глазами заказчика или подрядчика можно посмотреть в «Студии» — "
                                  "проект → «👁 Как видит заказчик». Ссылка осталась действующей.")
        if not getattr(self, "portal", None):
            return self.send(uid, t(self.lang_of(uid), "invite_bad"))
        inv = self.portal.invite(token)
        if inv and not lang_code and not self.s.get(f"tg:lang:{uid}"):
            self.s.put(f"tg:lang:{uid}", inv["lang"] or "ru")
        r = self.portal.use_invite(token, uid, name)
        lang = self.lang_of(uid)
        if not r:
            return self.send(uid, t(lang, "invite_bad"))
        role = "client" if r["kind"] == "client" else "crew"
        if not u:
            self.s.run("INSERT INTO users(tg_id, name, username, role, status, created, updated) VALUES(?, ?, ?, ?, 'active', ?, ?)",
                       uid, name, username, role, _now(), _now())
        elif u["status"] != "active" or u["role"] in (None,) + PORTAL_ROLES:
            if u["role"] == "client" and role == "crew" and u["status"] == "active":
                role = "client"                           # и заказчик, и подрядчик — главное, что заказчик
            self.s.run("UPDATE users SET role=?, status='active', partner_id=NULL, updated=? WHERE tg_id=?", role, _now(), uid)
        if r.get("replaced"):                             # к этой записи был привязан другой Telegram — у него доступа больше нет
            self.portal_unlinked(r["replaced"])
        u = self.user(uid)
        self.set_commands(u)
        self.sync_portal_menu(uid)
        p = r["project"] or {}
        self.send(uid, t(lang, "welcome_client" if r["kind"] == "client" else "welcome_crew", name=esc(name),
                         project=esc(self.loc(p.get("title") or "", lang)), menu=t(lang, "menu")),
                  [self.portal_row(lang, f"project={p.get('id')}")] if self.portal_row(lang) else None)
        what = "заказчик" if r["kind"] == "client" else "подрядчик"
        btn = self.studio_button("📁 Открыть проект", p.get("id")) if p.get("id") else None
        self.notify(f"✅ <b>{esc(r['ref']['name'])}</b> подключился к кабинету — {what} проекта «{esc(p.get('title') or '')}»"
                    f"\nTelegram: {esc(name)}" + (f" (@{esc(username)})" if username else ""),
                    roles=("designer",), rows=[btn] if btn else None)

    def portal_unlinked(self, tg_id):
        """Telegram отвязан от заказчика или подрядчика: если других проектов в кабинете нет — доступ к боту закрыт."""
        u = self.user(tg_id)
        if not u:
            return
        left = self.portal.projects_for(tg_id) if getattr(self, "portal", None) else []
        if not left and u["role"] in PORTAL_ROLES and u["status"] == "active":
            self.s.run("UPDATE users SET status='removed', updated=? WHERE tg_id=?", _now(), tg_id)
            self.send(tg_id, t(self.lang_of(tg_id), "closed"))
        self.sync_portal_menu(tg_id)

    def portal_relinked(self, tg_id):
        """Заказчика или подрядчика с привязанным Telegram снова добавили в проект — открыть доступ к боту обратно
        (если его закрыли, когда проектов не осталось; закрытое студией вручную — тоже, раз студия добавила снова)."""
        u = self.user(tg_id)
        if u and u["role"] in PORTAL_ROLES and u["status"] == "removed" and self.portal.projects_for(tg_id):
            self.s.run("UPDATE users SET status='active', updated=? WHERE tg_id=?", _now(), tg_id)
            row = self.portal_row(self.lang_of(tg_id))
            self.send(tg_id, self.portal_welcome(self.user(tg_id)), [row] if row else None)
        self.sync_portal_menu(tg_id)

    # ---------- сообщения в чате бота ----------
    def _map_put(self, chat_id, message_id, pid):
        if message_id:
            self.s.put(f"chatmap:{chat_id}:{message_id}", json.dumps({"p": int(pid), "t": int(time.time())}))

    def _map_get(self, chat_id, message_id):
        try:
            return int(json.loads(self.s.get(f"chatmap:{chat_id}:{message_id}") or "{}").get("p") or 0) or None
        except (ValueError, TypeError):
            return None

    def chat_reply(self, u, m):
        """Ответ студии свайпом на сообщение заказчика (или на своё сообщение в переписке) — в переписку проекта."""
        r = m.get("reply_to_message") or {}
        pid = self._map_get(u["tg_id"], r.get("message_id")) if r else None
        if not pid or not getattr(self, "portal", None):
            return False
        self._chat_in(u, pid, (m.get("text") or m.get("caption") or "").strip(), self.file_of(m), "studio")
        return True

    def portal_message(self, u, m, text, cmd):
        """Заказчик или подрядчик пишет в чат бота. Заказчик — в переписку своего проекта (один проект — сразу,
        несколько — спросить, к какому; ответ свайпом — в тот же проект). Подрядчику — как связаться со студией."""
        uid, lang = u["tg_id"], self.lang_of(u["tg_id"])
        if not getattr(self, "portal", None):
            return
        ps = self.portal.projects_for(uid)
        if cmd:                                           # /start, /help и любые команды — что это за бот
            row = self.portal_row(lang)
            return self.send(uid, self.portal_welcome(u), [row] if row and ps else None)
        mine = [p for p in ps if "client" in p["roles"]]
        if not mine:
            if not ps:
                return self.send(uid, t(lang, "no_projects"))
            return self.send(uid, t(lang, "crew_no_chat", phone=STUDIO["phone"], email=STUDIO["email"]))
        f = self.file_of(m)
        body = (m.get("text") or m.get("caption") or "").strip()
        if not body and not f:
            return
        r = m.get("reply_to_message") or {}
        pid = self._map_get(uid, r.get("message_id")) if r else None
        if pid not in [p["id"] for p in mine]:
            pid = mine[0]["id"] if len(mine) == 1 else None
        if not pid:
            self.s.put(f"pchat:{uid}", json.dumps({"text": body, "file": f, "ts": time.time()}, ensure_ascii=False))
            return self.send(uid, t(lang, "pick"), [[(p["title"][:60], f"pp:{p['id']}")] for p in mine[:8]])
        self._chat_in(u, pid, body, f, "client")

    def _chat_in(self, u, pid, text, f, kind):
        """Сообщение из чата бота → в переписку проекта (вложение — в файлы переписки) → остальным участникам."""
        uid = u["tg_id"]
        lang = "ru" if kind == "studio" else self.lang_of(uid)
        fid = None
        if f:
            if f.get("size") and f["size"] > CHAT_FILE_MAX:
                return self.send(uid, t(lang, "too_big"))
            try:
                with self._download(f["id"]) as r:
                    size = int(r.headers.get("Content-Length") or f["size"] or 0)
                    rec = self.crm.add_file(pid, "chat", f["name"], r, size, f["mime"], u["name"] or str(uid),
                                            tg_file_id=f"{f['kind']}:{f['id']}")
                fid = rec["id"]
            except Exception as e:  # noqa: BLE001
                self.log(f"переписка: файл не сохранён: {type(e).__name__}: {e}")
                if not text:
                    return self.send(uid, "⚠️ " + esc(str(e))[:300])
        author = STUDIO["designer"]["ru"] if kind == "studio" else (u["name"] or str(uid))
        try:
            msg = self.portal.post(pid, kind, uid, author, text, fid)
        except CrmError as e:
            return self.send(uid, "⚠️ " + esc(e))
        threading.Thread(target=self.chat_fanout, args=(msg["id"],), kwargs={"confirm_to": uid}, daemon=True).start()

    # ---------- рассылка сообщения переписки ----------
    def _recipients(self, pid, author_kind, author_tg):
        """Кому доставить: сообщение студии — заказчикам проекта; сообщение заказчика — дизайнерам и остальным заказчикам."""
        out = []
        if author_kind == "client":
            out += [(d["tg_id"], "ru", "studio", d["name"] or "") for d in self.active(("designer",))]
        for c in self.portal.chat_people(pid):
            tg = int(c["tg_id"])
            if tg == int(author_tg or 0):
                continue
            uu = self.user(tg)
            if uu and uu["status"] == "active":
                out.append((tg, self.lang_of(tg), "client", c["name"]))
        return out

    def chat_fanout(self, mid, confirm_to=None):
        m = self.portal.message(mid)
        if not m:
            return
        pid = m["project_id"]
        p = self.crm.one("SELECT id, title FROM projects WHERE id=?", pid) or {"id": pid, "title": ""}
        rec = self._recipients(pid, m["author_kind"], m["author_tg"])
        text = m["text"] or ""
        tr, src = {}, None
        if text and self.can_translate():
            for lang in sorted({x[1] for x in rec} | ({"ru"} if m["author_kind"] == "client" else set())):
                try:
                    r = translate_text(text, lang)
                except Exception as e:  # noqa: BLE001
                    self.log(f"перевод переписки ({lang}): ошибка {type(e).__name__}: {e}")
                    r = None
                if r:
                    src, tr[lang] = r
                    self.portal.set_translation(mid, lang, r[1], r[0])
        f = self.crm.one("SELECT * FROM files WHERE id=?", m["file_id"]) if m["file_id"] else None
        delivered, failed = [], []
        for tg, lang, kind, name in rec:
            if kind == "studio":
                head = f"💬 <b>{esc(m['author_name'])}</b> · «{esc(p['title'])}»"
                body = esc(text)
                if tr.get("ru"):
                    body += f"\n\n<i>Перевод на русский{(' ' + esc(lang_from(src))) if src else ''}:</i>\n{esc(tr['ru'])}"
                body += "\n\n<i>↩︎ Ответить: потяните сообщение влево</i>"
                rows = [self.studio_button("💬 Открыть переписку", query=f"project={pid}&chat=1")]
            else:
                who = self.designer_name(lang) if m["author_kind"] == "studio" else m["author_name"]
                head = f"💬 <b>{esc(who)}</b> · «{esc(self.loc(p['title'], lang))}»"
                body = esc(tr.get(lang) or text)
                if tr.get(lang):
                    body += f"\n\n<i>{t(lang, 'auto_tr')}</i>"
                rows = [self.portal_row(lang, f"project={pid}&tab=chat", "open_chat")]
            rows = [r for r in rows if r] or None
            ok, why, msg_id = self._send_chat(tg, head, body if text else "", f, rows)
            if ok:
                delivered.append(name)
                self._map_put(tg, msg_id, pid)
            else:
                failed.append((name, why))
        if confirm_to:
            u = self.user(confirm_to)
            if u and self.is_admin(u):
                line = ("✓ Отправлено: " + ", ".join(esc(x) for x in delivered)) if delivered else "⚠️ Никому не доставлено"
                if any(tr.get(x[1]) for x in rec if x[2] == "client"):
                    line += " (с переводом)"
                if failed:
                    line += "\n" + "\n".join(f"⚠️ {esc(n)} — не доставлено: {esc(self.why(w))}" for n, w in failed)
                if not rec:
                    line = "⚠️ Заказчики проекта ещё не подключены к кабинету — сообщение сохранено в переписке, но никому не отправлено."
                self.send(confirm_to, line)
            elif u:
                self.send(confirm_to, t(self.lang_of(confirm_to), "sent", project=esc(self.loc(p["title"], self.lang_of(confirm_to)))))
        elif m["author_kind"] == "studio" and failed:
            self.notify("⚠️ Сообщение в переписке «" + esc(p["title"]) + "» не доставлено:\n" +
                        "\n".join(f"{esc(n)} — {esc(self.why(w))}" for n, w in failed), roles=("designer",))

    @staticmethod
    def why(desc):
        try:
            from bot import why_failed
            return why_failed(desc)
        except ImportError:
            return desc

    def _send_chat(self, chat_id, head, body, f, rows):
        """Сообщение переписки в Telegram: текст или файл с подписью. (доставлено, причина, номер сообщения)."""
        text = head + ("\n" + body if body else "")
        if not f:
            p = {"chat_id": chat_id, "text": text[:4090], "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
            if rows:
                p["reply_markup"] = self.kb(rows)
            r = self.api("sendMessage", **p)
            return bool(r.get("ok")), str(r.get("description") or ""), (r.get("result") or {}).get("message_id")
        caption = text if len(text) <= 1000 else head
        ok, why, mid = self.send_file_r(chat_id, f, self.crm.file_path(f["id"], "o")[0], caption=caption, rows=rows)
        if ok and caption != text:
            self.send_r(chat_id, text[:4090])
        return ok, why, mid

    # ---------- кнопки заказчика ----------
    def portal_callback(self, who, msg, parts):
        uid, lang = who["tg_id"], self.lang_of(who["tg_id"])
        act = parts[0]
        if not getattr(self, "portal", None):
            return
        if act in ("pc", "pd"):
            sid = int(parts[1])
            try:
                st = self.portal.client_stage(uid, sid, "confirm" if act == "pc" else "dispute", "", who["name"] or str(uid))
            except CrmError:
                return self.edit(msg, t(lang, "stage_gone"))
            self.portal_event("stage_confirm" if act == "pc" else "stage_dispute", stage_id=st["id"], by=who["name"] or str(uid))
            row = self.portal_row(lang, f"project={st['project_id']}")
            return self.edit(msg, self._stage_text(st["id"], lang) + "\n\n" + t(lang, "you_confirmed" if act == "pc" else "you_disputed"),
                             [row] if row else None)
        if act == "pp":                                     # к какому проекту сообщение (у заказчика несколько проектов)
            pid = int(parts[1])
            try:
                d = json.loads(self.s.get(f"pchat:{uid}") or "{}")
            except ValueError:
                d = {}
            self.s.drop(f"pchat:{uid}")
            if not d or time.time() - d.get("ts", 0) > 1800 or not self.portal.client_of(uid, pid):
                return self.edit(msg, t(lang, "stage_gone"))
            p = self.crm.one("SELECT title FROM projects WHERE id=?", pid) or {}
            self.edit(msg, "→ «" + esc(p.get("title") or "") + "»")
            self._chat_in(who, pid, d.get("text") or "", d.get("file"), "client")

    # ---------- события из кабинета и «Студии» ----------
    def _stage_info(self, sid):
        st = self.crm.one("SELECT * FROM stages WHERE id=?", int(sid))
        if not st:
            return None
        k = self.crm.one("""SELECT l.trade AS link_trade, c.name, c.trade, c.tg_id FROM project_contractors l
                            JOIN contractors c ON c.id=l.contractor_id WHERE l.id=?""", st["link_id"]) or {}
        p = self.crm.one("SELECT id, title FROM projects WHERE id=?", st["project_id"]) or {}
        return st, k, p

    def _stage_text(self, sid, lang):
        info = self._stage_info(sid)
        if not info:
            return ""
        st, k, p = info
        trade = k.get("link_trade") or k.get("trade") or ""
        return t(lang, "stage_ask", project=esc(self.loc(p.get("title"), lang)), who=esc(k.get("name", "")) + (f" ({esc(self.loc(trade, lang))})" if trade else ""),
                 title=esc(self.loc(st["title"], lang) or "—"), amount=money(st["amount"], st["currency"], lang))

    def _client_tgs(self, pid):
        out = []
        for c in self.portal.chat_people(pid):
            uu = self.user(c["tg_id"])
            if uu and uu["status"] == "active":
                out.append(int(c["tg_id"]))
        return out

    def portal_event(self, kind, **kw):
        """Сообщения в Telegram после действий в кабинете и «Студии»."""
        if not getattr(self, "portal", None):
            return
        if kind in ("stage_saved", "stage_confirm", "stage_dispute"):
            info = self._stage_info(kw.get("stage_id"))
            if not info:
                return
            st, k, p = info
            pid = p.get("id")
            studio = self.studio_button("📁 Открыть проект", pid)
            if kind == "stage_saved":
                asked = []
                for tg in self._client_tgs(pid):
                    lang = self.lang_of(tg)
                    rows = [[(t(lang, "btn_confirm"), f"pc:{st['id']}"), (t(lang, "btn_dispute"), f"pd:{st['id']}")]]
                    row = self.portal_row(lang, f"project={pid}")
                    if self.send(tg, self._stage_text(st["id"], lang), rows + ([row] if row else [])):
                        asked.append(tg)
                line = f"{esc(st['title'] or '—')} — <b>{money(st['amount'], st['currency'])}</b>"
                if kw.get("by_contractor"):
                    self.notify(f"🧾 <b>Подрядчик {esc(k.get('name'))}</b> внёс сумму работ · «{esc(p.get('title'))}»\n{line}\n\n"
                                + ("Заказчику отправлено на подтверждение." if asked else
                                   "Заказчик не подключён к кабинету — подтвердить некому. Пригласите заказчика или проверьте сумму сами."),
                                roles=("designer",), rows=[studio] if studio else None)
                elif k.get("tg_id") and self._active(k["tg_id"]):
                    lang = self.lang_of(k["tg_id"])
                    row = self.portal_row(lang, f"project={pid}")
                    self.send(k["tg_id"], t(lang, "c_by_studio", project=esc(self.loc(p.get("title"), lang)), title=esc(self.loc(st["title"], lang) or "—"),
                                            amount=money(st["amount"], st["currency"], lang)), [row] if row else None)
                return
            ok = kind == "stage_confirm"
            note = st.get("dispute_note") or ""
            self.notify(("✓ " if ok else "⚠️ ") + f"<b>Заказчик {esc(kw.get('by'))}</b> " + ("подтвердил" if ok else "не согласен с")
                        + f" сумм{'у' if ok else 'ой'} · «{esc(p.get('title'))}»\n{esc(k.get('name'))}: {esc(st['title'] or '—')} — "
                        f"<b>{money(st['amount'], st['currency'])}</b>" + (f"\n«{esc(note)}»" if note else ""),
                        roles=("designer",), rows=[studio] if studio else None)
            if k.get("tg_id") and self._active(k["tg_id"]):
                lang = self.lang_of(k["tg_id"])
                row = self.portal_row(lang, f"project={pid}")
                self.send(k["tg_id"], t(lang, "c_confirmed" if ok else "c_disputed", project=esc(self.loc(p.get("title"), lang)),
                                        title=esc(self.loc(st["title"], lang) or "—"), amount=money(st["amount"], st["currency"], lang)),
                          [row] if row else None)
            return
        if kind == "link_new":
            link = self.crm.one("""SELECT l.project_id, l.trade AS link_trade, c.trade, c.tg_id FROM project_contractors l
                                   JOIN contractors c ON c.id=l.contractor_id WHERE l.id=?""", int(kw.get("link_id") or 0))
            if not link or not link["tg_id"]:
                return
            self.portal_relinked(link["tg_id"])           # кабинет закрывался, когда проектов не было — открыть снова
            if not self._active(link["tg_id"]):
                return
            p = self.crm.one("SELECT title FROM projects WHERE id=?", link["project_id"]) or {}
            lang = self.lang_of(link["tg_id"])
            trade = link["link_trade"] or link["trade"] or ""
            row = self.portal_row(lang, f"project={link['project_id']}")
            self.sync_portal_menu(link["tg_id"])
            self.send(link["tg_id"], t(lang, "link_new", project=esc(self.loc(p.get("title"), lang)), trade=f" ({esc(self.loc(trade, lang))})" if trade else ""),
                      [row] if row else None)
            return
        if kind in ("order_new", "order_delivered"):
            o = self.crm.one("SELECT * FROM orders WHERE id=?", int(kw.get("order_id") or 0))
            if not o:
                return
            p = self.crm.one("SELECT id, title FROM projects WHERE id=?", o["project_id"]) or {}
            rest = None
            if kind == "order_delivered":
                x = next((y for y in (self.crm.extras(o["project_id"]).get(o["project_id"]) or {}).get("orders", []) if y["id"] == o["id"]), None)
                rest = x["money"]["rest"] if x else None
            for tg in self._client_tgs(o["project_id"]):
                lang = self.lang_of(tg)
                if kind == "order_new":
                    text = t(lang, "order_new", project=esc(self.loc(p.get("title"), lang)), title=esc(self.loc(o["title"], lang)), amount=money(o["price"], o["currency"], lang),
                             planned=t(lang, "planned", date=dmy(o["planned"])) if o["planned"] else "")
                else:
                    text = t(lang, "order_delivered", project=esc(self.loc(p.get("title"), lang)), title=esc(self.loc(o["title"], lang)),
                             rest=t(lang, "rest", amount=money(rest, o["currency"], lang)) if rest else t(lang, "paid_full"))
                row = self.portal_row(lang, f"project={o['project_id']}&tab=money")
                self.send(tg, text, [row] if row else None)
            return
        if kind == "service_new":
            s = self.crm.one("SELECT * FROM services WHERE id=?", int(kw.get("service_id") or 0))
            if not s:
                return
            p = self.crm.one("SELECT id, title FROM projects WHERE id=?", s["project_id"]) or {}
            for tg in self._client_tgs(s["project_id"]):
                lang = self.lang_of(tg)
                monthly = s["kind"] == "monthly"
                text = t(lang, "service_new", project=esc(self.loc(p.get("title"), lang)), title=esc(self.loc(s["title"], lang)), amount=money(s["amount"], "EUR", lang),
                         per=t(lang, "per_month") if monthly else "", when=t(lang, "first_pay" if monthly else "pay_by", date=dmy(s["start"])))
                row = self.portal_row(lang, f"project={s['project_id']}&tab=money")
                self.send(tg, text, [row] if row else None)

    def _active(self, tg):
        uu = self.user(tg)
        return bool(uu and uu["status"] == "active")

    # ---------- напоминания об оплате доп. услуг ----------
    def portal_reminders(self, log=print, now=None):
        """Раз в минуту (фоновые дела сервиса): днём — напоминания об оплате доп. услуг заказчикам и Ирине;
        раз в сутки — забыть старые привязки «ответ свайпом»."""
        if not getattr(self, "portal", None):
            return 0
        now = now or datetime.now(timezone.utc)
        local = now.astimezone(TZ)
        day = local.date().isoformat()
        if self.s.get("chatmap:pruned") != day:
            self.s.put("chatmap:pruned", day)
            edge = time.time() - CHAT_MAP_DAYS * 86400
            for r in self.s.all("SELECT key, value FROM state WHERE key LIKE 'chatmap:%:%'"):
                try:
                    if json.loads(r["value"]).get("t", 0) < edge:
                        self.s.drop(r["key"])
                except (ValueError, AttributeError):
                    self.s.drop(r["key"])
        if not 10 <= local.hour < 20:
            return 0
        sent = 0
        for x in self.portal.due_reminders(local.date()):
            p, s = x["project"], x["service"]
            title = s["title"]
            for tg in self._client_tgs(p["id"]):
                lang = self.lang_of(tg)
                row = self.portal_row(lang, f"project={p['id']}&tab=money")
                self.send(tg, t(lang, "remind_due" if x["stage"] == "due" else "remind_overdue", project=esc(self.loc(p["title"], lang)),
                                title=esc(self.loc(title, lang)), amount=money(x["rest"], "EUR", lang), date=dmy(x["due"])), [row] if row else None)
            studio = self.studio_button("📁 Открыть проект", p["id"])
            self.notify(("🔔 <b>Срок оплаты сегодня</b>" if x["stage"] == "due" else "🔔 <b>Не оплачено 7 дней</b>")
                        + f" · «{esc(p['title'])}»\n{esc(title)}: <b>{money(x['rest'])}</b> — срок {dmy(x['due'])}"
                        + (f"\nВсего по услуге не оплачено: {money(x['debt'])}" if x["debt"] > x["rest"] + 0.005 else "")
                        + ("\nЗаказчику отправлено напоминание." if self._client_tgs(p["id"]) else
                           "\nЗаказчик не подключён к кабинету — напомните ему сами."),
                        roles=("designer",), rows=[studio] if studio else None)
            self.portal.reminded(x["key"])
            sent += 1
            log(f"кабинет: напоминание об оплате «{title}» ({x['due']}, {x['stage']})")
        return sent


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
