#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Кабинеты в боте студии (часть класса Bot): заказчик, подрядчик, работник подрядчика, наблюдатель — и разговоры проекта.

  • Ссылка-приглашение t.me/<бот>?start=pj_… : заказчику — из проекта в «Студии»; подрядчику — один раз из «Студии»
    (дальше он видит все проекты, куда его добавят); работнику — от его подрядчика из кабинета («Бригада»).
    Человек нажимает «Старт» — Telegram привязан, слева от поля ввода появляется кнопка «Мой проект» (на его языке).
  • Разговоры (crm_portal.py): заказчик — со студией и с любым подрядчиком проекта (студия видит, вступает, когда
    ответит); подрядчик — со студией, с заказчиками, в группах; работник — со студией и в группах (его разговоры видит
    его подрядчик); группы собирает Ирина. Написанное прямо в чат бота уходит в «свой» разговор со студией, ответ свайпом —
    в тот разговор, на сообщение которого отвечают. Каждому — с переводом на его язык; Ирине — на русский.
  • Наблюдатель «Разработчик ПО» получает тихие копии всех сообщений (🧪) — для тестирования.
  • Суммы работ подрядчиков: внесла студия или сам подрядчик — заказчику приходит «Подтверждаю / Не согласен».
  • Товары и доп. услуги: заказчику — сообщение о новом товаре, услуге, доставке (если в «Студии» отмечено «Сообщить»).
  • Документы подрядчиков и работников: студии — всегда; подрядчику — от его работников; заказчику — если открыт ему.
  • Напоминания об оплате доп. услуг (помесячно и разовых): заказчику и Ирине — в день оплаты и через 7 дней, если
    не оплачено (днём, 10:00–20:00 по Братиславе).
Тексты для заказчиков, подрядчиков и работников — на пяти языках (RU, UA, EN, SK, DE) по языку их Telegram или выбранному
в кабинете. Только стандартная библиотека Python 3."""
import html
import json
import threading
import time
from datetime import date, datetime, timezone

from crm import FILE_CATS, TZ, CrmError
from crm_portal import STUDIO, ui_lang
from langs import pack

try:
    from translate import lang_from, provider as translate_provider, translate_text
except ImportError:                    # pragma: no cover
    def translate_provider():
        return None

    def translate_text(text, target):
        return None

    def lang_from(code):
        return ""

PORTAL_ROLES = ("client", "crew", "worker", "assistant")   # заказчик, подрядчик (руководитель), работник подрядчика, сотрудник студии
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
              "оплатить, доп. услуги и товары, документы и визуализации, подрядчики и переписка с Ириной и с подрядчиками.\n\n"
              "Открыть кабинет — кнопка «{menu}» слева от поля ввода. Написать Ирине можно прямо сюда, в чат.",
        "uk": "Добрий день, {name}! Це кабінет вашого проєкту «{project}» у студії DUMSKAYA DESIGN: оплати і що залишилося "
              "сплатити, додаткові послуги й товари, документи й візуалізації, підрядники і листування з Іриною та з підрядниками.\n\n"
              "Відкрити кабінет — кнопка «{menu}» ліворуч від поля введення. Написати Ірині можна просто сюди, в чат.",
        "en": "Hello {name}! This is the app for your project “{project}” with DUMSKAYA DESIGN: payments and what is left to pay, "
              "extra services and furniture orders, documents and renderings, contractors and your chats with Irina and the contractors.\n\n"
              "To open it, tap “{menu}” next to the message field. You can also write to Irina right here in this chat.",
        "sk": "Dobrý deň, {name}! Toto je aplikácia vášho projektu „{project}“ v štúdiu DUMSKAYA DESIGN: platby a čo ešte "
              "zostáva zaplatiť, doplnkové služby a objednaný tovar, dokumenty a vizualizácie, remeselníci a konverzácie s Irinou "
              "aj s remeselníkmi.\n\nOtvoríte ju tlačidlom „{menu}“ vedľa poľa na písanie. Irine môžete napísať aj priamo sem do chatu.",
        "de": "Guten Tag, {name}! Das ist die App zu Ihrem Projekt „{project}“ bei DUMSKAYA DESIGN: Zahlungen und offene Beträge, "
              "Zusatzleistungen und bestellte Möbel, Unterlagen und Visualisierungen, Handwerker und die Chats mit Irina und den Handwerkern.\n\n"
              "Öffnen Sie sie über „{menu}“ neben dem Eingabefeld. Sie können Irina auch direkt hier im Chat schreiben."},
    "welcome_crew": {
        "ru": "Здравствуйте, {name}! Это кабинет подрядчика студии DUMSKAYA DESIGN. Здесь все проекты студии, в которых вы "
              "участвуете{now}: документация и визуализации, контакты заказчика, ваши расчёты со студией, переписка со студией "
              "и с заказчиком. Можно подключить своих работников («Бригада») и прикреплять фото выполненных работ и документы.\n\n"
              "Открыть кабинет — кнопка «{menu}» слева от поля ввода. Написать студии можно прямо сюда, в чат.",
        "uk": "Добрий день, {name}! Це кабінет підрядника студії DUMSKAYA DESIGN. Тут усі проєкти студії, у яких ви "
              "берете участь{now}: документація й візуалізації, контакти замовника, ваші розрахунки зі студією, листування зі студією "
              "і з замовником. Можна підключити своїх працівників («Бригада») і додавати фото виконаних робіт і документи.\n\n"
              "Відкрити кабінет — кнопка «{menu}» ліворуч від поля введення. Написати студії можна просто сюди, в чат.",
        "en": "Hello {name}! This is the contractor app of DUMSKAYA DESIGN. Here are all the studio’s projects you work on{now}: "
              "documents and renderings, the client’s contacts, your account with the studio, chats with the studio and the client. "
              "You can connect your workers (“Team”) and attach photos of finished work and documents.\n\n"
              "To open it, tap “{menu}” next to the message field. You can also write to the studio right here in this chat.",
        "sk": "Dobrý deň, {name}! Toto je aplikácia pre dodávateľov štúdia DUMSKAYA DESIGN. Nájdete tu všetky projekty štúdia, "
              "na ktorých pracujete{now}: dokumentáciu a vizualizácie, kontakty na klienta, vyúčtovanie so štúdiom, konverzácie "
              "so štúdiom a s klientom. Môžete pripojiť svojich pracovníkov („Tím“) a pridávať fotky hotovej práce a dokumenty.\n\n"
              "Otvoríte ju tlačidlom „{menu}“ vedľa poľa na písanie. Štúdiu môžete napísať aj priamo sem do chatu.",
        "de": "Guten Tag, {name}! Das ist die Handwerker-App von DUMSKAYA DESIGN. Hier finden Sie alle Projekte des Studios, an denen "
              "Sie arbeiten{now}: Unterlagen und Visualisierungen, Kontakte des Kunden, Ihre Abrechnung mit dem Studio, Chats mit dem "
              "Studio und dem Kunden. Sie können Ihre Mitarbeiter verbinden („Team“) und Fotos fertiger Arbeiten und Unterlagen anhängen.\n\n"
              "Öffnen Sie sie über „{menu}“ neben dem Eingabefeld. Sie können dem Studio auch direkt hier im Chat schreiben."},
    "now": {"ru": " (сейчас — «{project}»)", "uk": " (зараз — «{project}»)", "en": " (now: “{project}”)", "sk": " (teraz: „{project}“)",
            "de": " (derzeit: „{project}“)"},
    "welcome_worker": {
        "ru": "Здравствуйте, {name}! Это кабинет работника студии DUMSKAYA DESIGN, вас подключил(а) {head}. Здесь объекты, "
              "на которые вас отправляют: адрес, документация и визуализации, переписка со студией. Можно прикреплять фото и "
              "документы и выбирать, кто их видит.\n\nОткрыть кабинет — кнопка «{menu}» слева от поля ввода. Написать студии "
              "можно прямо сюда, в чат.",
        "uk": "Добрий день, {name}! Це кабінет працівника студії DUMSKAYA DESIGN, вас підключив(-ла) {head}. Тут об’єкти, "
              "на які вас направляють: адреса, документація й візуалізації, листування зі студією. Можна додавати фото й "
              "документи і вибирати, хто їх бачить.\n\nВідкрити кабінет — кнопка «{menu}» ліворуч від поля введення. Написати "
              "студії можна просто сюди, в чат.",
        "en": "Hello {name}! This is the worker app of DUMSKAYA DESIGN — {head} has connected you. Here are the sites you are sent to: "
              "address, documents and renderings, your chat with the studio. You can attach photos and documents and choose who sees them.\n\n"
              "To open it, tap “{menu}” next to the message field. You can also write to the studio right here in this chat.",
        "sk": "Dobrý deň, {name}! Toto je aplikácia pre pracovníkov štúdia DUMSKAYA DESIGN, pripojil(a) vás {head}. Nájdete tu "
              "stavby, na ktoré vás posielajú: adresu, dokumentáciu a vizualizácie, konverzáciu so štúdiom. Môžete pridávať fotky "
              "a dokumenty a vybrať, kto ich vidí.\n\nOtvoríte ju tlačidlom „{menu}“ vedľa poľa na písanie. Štúdiu môžete "
              "napísať aj priamo sem do chatu.",
        "de": "Guten Tag, {name}! Das ist die Mitarbeiter-App von DUMSKAYA DESIGN — {head} hat Sie verbunden. Hier finden Sie die "
              "Baustellen, auf die Sie geschickt werden: Adresse, Unterlagen und Visualisierungen, Ihren Chat mit dem Studio. Sie können "
              "Fotos und Unterlagen anhängen und auswählen, wer sie sieht.\n\nÖffnen Sie sie über „{menu}“ neben dem Eingabefeld. "
              "Sie können dem Studio auch direkt hier im Chat schreiben."},
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
    "read_only": {
        "ru": "Эту переписку вы только видите — ответить в ней нельзя. Написать студии — просто отправьте сообщение сюда, без ответа.",
        "uk": "Це листування ви лише бачите — відповісти в ньому не можна. Написати студії — просто надішліть повідомлення сюди, без відповіді.",
        "en": "You can only read this conversation — replies are not possible here. To write to the studio, just send a message here, not as a reply.",
        "sk": "Túto konverzáciu môžete len čítať — odpovedať v nej nemožno. Ak chcete napísať štúdiu, pošlite správu sem, nie ako odpoveď.",
        "de": "Diesen Chat können Sie nur lesen — antworten ist hier nicht möglich. Um dem Studio zu schreiben, senden Sie einfach eine Nachricht hierher, nicht als Antwort."},
    "reply_hint": {"ru": "↩︎ Ответить: потяните сообщение влево", "uk": "↩︎ Відповісти: потягніть повідомлення вліво",
                   "en": "↩︎ To reply, swipe this message to the left", "sk": "↩︎ Odpovedať: potiahnite správu doľava",
                   "de": "↩︎ Antworten: Nachricht nach links ziehen"},
    "ctx_group": {"ru": "Группа «{title}»", "uk": "Група «{title}»", "en": "Group “{title}”", "sk": "Skupina „{title}“", "de": "Gruppe „{title}“"},
    "ctx_watch": {"ru": "👁 Студия и {name} — вы видите, отвечает {name}", "uk": "👁 Студія і {name} — ви бачите, відповідає {name}",
                  "en": "👁 Studio and {name} — you can read along, {name} replies", "sk": "👁 Štúdio a {name} — vidíte, odpovedá {name}",
                  "de": "👁 Studio und {name} — Sie lesen mit, {name} antwortet"},
    "role_client": {"ru": "заказчик", "uk": "замовник", "en": "client", "sk": "klient", "de": "Kunde"},
    "crew_joined": {"ru": "✅ {name} — в боте. Отметьте в кабинете («Бригада»), на каких объектах работает этот человек.",
                    "uk": "✅ {name} — у боті. Позначте в кабінеті («Бригада»), на яких об’єктах працює ця людина.",
                    "en": "✅ {name} has joined the bot. Mark in the app (“Team”) which sites this person works on.",
                    "sk": "✅ {name} je v bote. V aplikácii („Tím“) označte, na ktorých stavbách táto osoba pracuje.",
                    "de": "✅ {name} ist jetzt im Bot. Markieren Sie in der App („Team“), auf welchen Baustellen diese Person arbeitet."},
    "crew_assigned": {"ru": "📁 Вас отметили на объекте «{project}». Документация и переписка со студией — в кабинете.",
                      "uk": "📁 Вас позначили на об’єкті «{project}». Документація й листування зі студією — у кабінеті.",
                      "en": "📁 You have been assigned to the site “{project}”. Documents and the chat with the studio are in the app.",
                      "sk": "📁 Priradili vás na stavbu „{project}“. Dokumentácia a konverzácia so štúdiom sú v aplikácii.",
                      "de": "📁 Sie wurden der Baustelle „{project}“ zugeteilt. Unterlagen und der Chat mit dem Studio sind in der App."},
    "group_new": {"ru": "👥 {who} создала группу «{title}» · «{project}»\nВ группе: {members}.\nПисать в группу — в кабинете или ответом на её сообщения (потяните сообщение влево).",
                  "uk": "👥 {who} створила групу «{title}» · «{project}»\nУ групі: {members}.\nПисати в групу — у кабінеті або відповіддю на її повідомлення (потягніть повідомлення вліво).",
                  "en": "👥 {who} has created the group “{title}” · “{project}”\nMembers: {members}.\nWrite to the group in the app or reply to its messages (swipe a message to the left).",
                  "sk": "👥 {who} vytvorila skupinu „{title}“ · „{project}“\nV skupine: {members}.\nDo skupiny píšte v aplikácii alebo odpoveďou na jej správy (potiahnite správu doľava).",
                  "de": "👥 {who} hat die Gruppe „{title}“ erstellt · „{project}“\nMitglieder: {members}.\nIn die Gruppe schreiben Sie in der App oder als Antwort auf ihre Nachrichten (Nachricht nach links ziehen)."},
    "doc_new": {"ru": "📎 <b>Новый документ</b> · «{project}»\n{who}: {title}", "uk": "📎 <b>Новий документ</b> · «{project}»\n{who}: {title}",
                "en": "📎 <b>New document</b> · “{project}”\n{who}: {title}", "sk": "📎 <b>Nový dokument</b> · „{project}“\n{who}: {title}",
                "de": "📎 <b>Neues Dokument</b> · „{project}“\n{who}: {title}"},
    "no_projects": {"ru": "В кабинете пока нет проектов. Когда студия добавит вас в проект, он появится здесь сам.",
                    "uk": "У кабінеті поки немає проєктів. Коли студія додасть вас до проєкту, він з’явиться тут сам.",
                    "en": "There are no projects in your app yet. When the studio adds you to a project, it will appear here.",
                    "sk": "V aplikácii zatiaľ nie sú žiadne projekty. Keď vás štúdio pridá do projektu, objaví sa tu.",
                    "de": "In Ihrer App gibt es noch keine Projekte. Sobald das Studio Sie zu einem Projekt hinzufügt, erscheint es hier."},
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
    "link_new": {"ru": "📁 Вас добавили в проект «{project}»{trade}. Документация, контакты заказчика и переписка — в кабинете.",
                 "uk": "📁 Вас додали до проєкту «{project}»{trade}. Документація, контакти замовника й листування — у кабінеті.",
                 "en": "📁 You have been added to the project “{project}”{trade}. Documents, the client’s contacts and chats are in the app.",
                 "sk": "📁 Pridali vás do projektu „{project}“{trade}. Dokumentácia, kontakty na klienta a konverzácie sú v aplikácii.",
                 "de": "📁 Sie wurden zum Projekt „{project}“{trade} hinzugefügt. Unterlagen, Kontakte des Kunden und Chats finden Sie in der App."},
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
        "ru": "Здравствуйте, {name}! Это ссылка на кабинет подрядчика студии DUMSKAYA DESIGN в Telegram: проекты студии, в которых "
              "вы участвуете, документация и визуализации, контакты заказчика, расчёты и переписка со студией; там же можно подключить "
              "своих работников. Откройте её в Telegram и нажмите кнопку внизу экрана («Старт»):\n{link}\n\n"
              "Ссылка личная, для одного человека, и действует 14 дней. Подключиться нужно один раз — новые проекты появятся в кабинете сами.",
        "uk": "Добрий день, {name}! Це посилання на кабінет підрядника студії DUMSKAYA DESIGN у Telegram: проєкти студії, у яких "
              "ви берете участь, документація й візуалізації, контакти замовника, розрахунки й листування зі студією; там само можна "
              "підключити своїх працівників. Відкрийте його в Telegram і натисніть кнопку внизу екрана («Почати»):\n{link}\n\n"
              "Посилання особисте, для однієї людини, і діє 14 днів. Підключитися треба один раз — нові проєкти з’являться в кабінеті самі.",
        "en": "Hello {name}! Here is the link to the DUMSKAYA DESIGN contractor app in Telegram: the studio’s projects you work on, "
              "documents and renderings, the client’s contacts, your account and chat with the studio; you can also connect your workers there. "
              "Open it in Telegram and tap the button at the bottom (“Start”):\n{link}\n\n"
              "The link is personal, for one person, and is valid for 14 days. You only need to connect once — new projects will appear in the app automatically.",
        "sk": "Dobrý deň, {name}! Posielame odkaz na aplikáciu pre dodávateľov štúdia DUMSKAYA DESIGN v Telegrame: projekty štúdia, "
              "na ktorých pracujete, dokumentácia a vizualizácie, kontakty na klienta, vyúčtovanie a konverzácia so štúdiom; môžete tam "
              "pripojiť aj svojich pracovníkov. Otvorte ho v Telegrame a ťuknite na tlačidlo dole („Štart“):\n{link}\n\n"
              "Odkaz je osobný, pre jednu osobu, a platí 14 dní. Pripojiť sa stačí raz — nové projekty sa v aplikácii objavia samy.",
        "de": "Guten Tag, {name}! Hier ist der Link zur Handwerker-App von DUMSKAYA DESIGN in Telegram: die Projekte des Studios, an denen "
              "Sie arbeiten, Unterlagen und Visualisierungen, Kontakte des Kunden, Abrechnung und Chat mit dem Studio; dort können Sie auch "
              "Ihre Mitarbeiter verbinden. Öffnen Sie ihn in Telegram und tippen Sie unten auf die Schaltfläche („Starten“):\n{link}\n\n"
              "Der Link ist persönlich, für eine Person, und 14 Tage gültig. Verbinden müssen Sie sich nur einmal — neue Projekte erscheinen automatisch in der App."},
    "invite_crew": {
        "ru": "Здравствуйте, {name}! {head} приглашает вас в кабинет работника студии DUMSKAYA DESIGN в Telegram: объекты, на которые "
              "вас отправляют, документация и переписка со студией. Откройте ссылку в Telegram и нажмите кнопку внизу экрана («Старт»):\n"
              "{link}\n\nСсылка личная, для одного человека, и действует 14 дней.",
        "uk": "Добрий день, {name}! {head} запрошує вас до кабінету працівника студії DUMSKAYA DESIGN у Telegram: об’єкти, на які "
              "вас направляють, документація й листування зі студією. Відкрийте посилання в Telegram і натисніть кнопку внизу екрана («Почати»):\n"
              "{link}\n\nПосилання особисте, для однієї людини, і діє 14 днів.",
        "en": "Hello {name}! {head} invites you to the DUMSKAYA DESIGN worker app in Telegram: the sites you are sent to, documents and "
              "your chat with the studio. Open the link in Telegram and tap the button at the bottom (“Start”):\n"
              "{link}\n\nThe link is personal, for one person, and is valid for 14 days.",
        "sk": "Dobrý deň, {name}! {head} vás pozýva do aplikácie pre pracovníkov štúdia DUMSKAYA DESIGN v Telegrame: stavby, na ktoré "
              "vás posielajú, dokumentácia a konverzácia so štúdiom. Otvorte odkaz v Telegrame a ťuknite na tlačidlo dole („Štart“):\n"
              "{link}\n\nOdkaz je osobný, pre jednu osobu, a platí 14 dní.",
        "de": "Guten Tag, {name}! {head} lädt Sie in die Mitarbeiter-App von DUMSKAYA DESIGN in Telegram ein: die Baustellen, auf die "
              "Sie geschickt werden, Unterlagen und Ihr Chat mit dem Studio. Öffnen Sie den Link in Telegram und tippen Sie unten auf die Schaltfläche („Starten“):\n"
              "{link}\n\nDer Link ist persönlich, für eine Person, und 14 Tage gültig."},
    # поставщики (плитка, свет, полы, сантехника…) — тот же кабинет подрядчика, вместо работ — поставки (24.10.2026, ночь)
    "welcome_supplier": {
        "ru": "Здравствуйте, {name}! Это кабинет поставщика студии DUMSKAYA DESIGN. Здесь все проекты студии, для которых вы поставляете "
              "материалы{now}: документация и визуализации, контакты заказчика, ваши поставки и расчёты со студией, переписка со студией "
              "и с заказчиком. Можно подключить своих сотрудников («Сотрудники») и прикреплять счета, спецификации и фото.\n\n"
              "Открыть кабинет — кнопка «{menu}» слева от поля ввода. Написать студии можно прямо сюда, в чат.",
        "uk": "Добрий день, {name}! Це кабінет постачальника студії DUMSKAYA DESIGN. Тут усі проєкти студії, для яких ви постачаєте "
              "матеріали{now}: документація й візуалізації, контакти замовника, ваші поставки й розрахунки зі студією, листування зі студією "
              "і з замовником. Можна підключити своїх співробітників («Співробітники») і додавати рахунки, специфікації та фото.\n\n"
              "Відкрити кабінет — кнопка «{menu}» ліворуч від поля введення. Написати студії можна просто сюди, в чат.",
        "en": "Hello {name}! This is the supplier app of DUMSKAYA DESIGN. Here are all the studio’s projects you supply materials for{now}: "
              "documents and renderings, the client’s contacts, your deliveries and account with the studio, chats with the studio and the client. "
              "You can connect your staff (“Staff”) and attach invoices, specifications and photos.\n\n"
              "To open it, tap “{menu}” next to the message field. You can also write to the studio right here in this chat.",
        "sk": "Dobrý deň, {name}! Toto je aplikácia pre dodávateľov materiálu štúdia DUMSKAYA DESIGN. Nájdete tu všetky projekty štúdia, pre ktoré "
              "dodávate materiál{now}: dokumentáciu a vizualizácie, kontakty na klienta, vaše dodávky a vyúčtovanie so štúdiom, konverzácie so štúdiom "
              "a s klientom. Môžete pripojiť svojich zamestnancov („Zamestnanci“) a pridávať faktúry, špecifikácie a fotky.\n\n"
              "Otvoríte ju tlačidlom „{menu}“ vedľa poľa na písanie. Štúdiu môžete napísať aj priamo sem do chatu.",
        "de": "Guten Tag, {name}! Das ist die Lieferanten-App von DUMSKAYA DESIGN. Hier finden Sie alle Projekte des Studios, für die Sie Material "
              "liefern{now}: Unterlagen und Visualisierungen, Kontakte des Kunden, Ihre Lieferungen und die Abrechnung mit dem Studio, Chats mit dem "
              "Studio und dem Kunden. Sie können Ihre Mitarbeiter verbinden („Mitarbeiter“) und Rechnungen, Spezifikationen und Fotos anhängen.\n\n"
              "Öffnen Sie sie über „{menu}“ neben dem Eingabefeld. Sie können dem Studio auch direkt hier im Chat schreiben."},
    "invite_supplier": {
        "ru": "Здравствуйте, {name}! Это ссылка на кабинет поставщика студии DUMSKAYA DESIGN в Telegram: проекты студии, для которых вы "
              "поставляете материалы, документация и визуализации, контакты заказчика, поставки, расчёты и переписка со студией; там же можно "
              "подключить своих сотрудников. Откройте её в Telegram и нажмите кнопку внизу экрана («Старт»):\n{link}\n\n"
              "Ссылка личная, для одного человека, и действует 14 дней. Подключиться нужно один раз — новые проекты появятся в кабинете сами.",
        "uk": "Добрий день, {name}! Це посилання на кабінет постачальника студії DUMSKAYA DESIGN у Telegram: проєкти студії, для яких ви "
              "постачаєте матеріали, документація й візуалізації, контакти замовника, поставки, розрахунки й листування зі студією; там само можна "
              "підключити своїх співробітників. Відкрийте його в Telegram і натисніть кнопку внизу екрана («Почати»):\n{link}\n\n"
              "Посилання особисте, для однієї людини, і діє 14 днів. Підключитися треба один раз — нові проєкти з’являться в кабінеті самі.",
        "en": "Hello {name}! Here is the link to the DUMSKAYA DESIGN supplier app in Telegram: the studio’s projects you supply materials for, "
              "documents and renderings, the client’s contacts, your deliveries, account and chat with the studio; you can also connect your staff there. "
              "Open it in Telegram and tap the button at the bottom (“Start”):\n{link}\n\n"
              "The link is personal, for one person, and is valid for 14 days. You only need to connect once — new projects will appear in the app automatically.",
        "sk": "Dobrý deň, {name}! Posielame odkaz na aplikáciu pre dodávateľov materiálu štúdia DUMSKAYA DESIGN v Telegrame: projekty štúdia, pre ktoré "
              "dodávate materiál, dokumentácia a vizualizácie, kontakty na klienta, dodávky, vyúčtovanie a konverzácia so štúdiom; môžete tam pripojiť "
              "aj svojich zamestnancov. Otvorte ho v Telegrame a ťuknite na tlačidlo dole („Štart“):\n{link}\n\n"
              "Odkaz je osobný, pre jednu osobu, a platí 14 dní. Pripojiť sa stačí raz — nové projekty sa v aplikácii objavia samy.",
        "de": "Guten Tag, {name}! Hier ist der Link zur Lieferanten-App von DUMSKAYA DESIGN in Telegram: die Projekte des Studios, für die Sie Material "
              "liefern, Unterlagen und Visualisierungen, Kontakte des Kunden, Lieferungen, Abrechnung und Chat mit dem Studio; dort können Sie auch Ihre "
              "Mitarbeiter verbinden. Öffnen Sie ihn in Telegram und tippen Sie unten auf die Schaltfläche („Starten“):\n{link}\n\n"
              "Der Link ist persönlich, für eine Person, und 14 Tage gültig. Verbinden müssen Sie sich nur einmal — neue Projekte erscheinen automatisch in der App."},
    "supply_ask": {"ru": "🧾 <b>Сумма поставки на подтверждение</b> · «{project}»\n{who}: {title} — <b>{amount}</b>\n\nЕсли сумма верная — нажмите «Подтверждаю».",
                   "uk": "🧾 <b>Сума поставки на підтвердження</b> · «{project}»\n{who}: {title} — <b>{amount}</b>\n\nЯкщо сума правильна — натисніть «Підтверджую».",
                   "en": "🧾 <b>Please confirm the delivery amount</b> · “{project}”\n{who}: {title} — <b>{amount}</b>\n\nIf the amount is correct, tap “I confirm”.",
                   "sk": "🧾 <b>Potvrďte sumu dodávky</b> · „{project}“\n{who}: {title} — <b>{amount}</b>\n\nAk je suma správna, ťuknite na „Potvrdzujem“.",
                   "de": "🧾 <b>Bitte bestätigen Sie den Lieferbetrag</b> · „{project}“\n{who}: {title} — <b>{amount}</b>\n\nWenn der Betrag stimmt, tippen Sie auf „Ich bestätige“."},
    "c_by_studio_sup": {"ru": "🧾 Студия внесла сумму вашей поставки · «{project}»\n{title} — <b>{amount}</b>",
                        "uk": "🧾 Студія внесла суму вашої поставки · «{project}»\n{title} — <b>{amount}</b>",
                        "en": "🧾 The studio has entered the amount of your delivery · “{project}”\n{title} — <b>{amount}</b>",
                        "sk": "🧾 Štúdio zadalo sumu vašej dodávky · „{project}“\n{title} — <b>{amount}</b>",
                        "de": "🧾 Das Studio hat den Betrag Ihrer Lieferung eingetragen · „{project}“\n{title} — <b>{amount}</b>"},
    "crew_joined_sup": {"ru": "✅ {name} — в боте. Отметьте в кабинете («Сотрудники»), с какими проектами работает этот человек.",
                        "uk": "✅ {name} — у боті. Позначте в кабінеті («Співробітники»), з якими проєктами працює ця людина.",
                        "en": "✅ {name} has joined the bot. Mark in the app (“Staff”) which projects this person works on.",
                        "sk": "✅ {name} je v bote. V aplikácii („Zamestnanci“) označte, na ktorých projektoch táto osoba pracuje.",
                        "de": "✅ {name} ist jetzt im Bot. Markieren Sie in der App („Mitarbeiter“), an welchen Projekten diese Person arbeitet."},
    # сотрудники студии (ассистент, визуализатор, чертёжник, комплектатор) — ссылку даёт Ирина (24.10.2026, ночь)
    "welcome_assistant": {
        "ru": "Здравствуйте, {name}! Это кабинет сотрудника студии DUMSKAYA DESIGN. Здесь проекты, на которые вас назначила Ирина{now}: "
              "участники, документация и визуализации, документы подрядчиков и все разговоры проекта — вы пишете в них от имени студии. "
              "Можно добавлять файлы в разделы проекта.\n\nОткрыть кабинет — кнопка «{menu}» слева от поля ввода. "
              "Ответить на сообщение разговора — потяните его влево.",
        "uk": "Добрий день, {name}! Це кабінет співробітника студії DUMSKAYA DESIGN. Тут проєкти, на які вас призначила Ірина{now}: "
              "учасники, документація й візуалізації, документи підрядників і всі розмови проєкту — ви пишете в них від імені студії. "
              "Можна додавати файли в розділи проєкту.\n\nВідкрити кабінет — кнопка «{menu}» ліворуч від поля введення. "
              "Відповісти на повідомлення розмови — потягніть його вліво.",
        "en": "Hello {name}! This is the studio staff app of DUMSKAYA DESIGN. Here are the projects Irina has assigned you to{now}: participants, "
              "documents and renderings, contractors’ documents and all project chats — you write in them on behalf of the studio. "
              "You can add files to the project sections.\n\nTo open it, tap “{menu}” next to the message field. "
              "To reply to a chat message, swipe it to the left.",
        "sk": "Dobrý deň, {name}! Toto je aplikácia pre zamestnancov štúdia DUMSKAYA DESIGN. Nájdete tu projekty, na ktoré vás pridelila Irina{now}: "
              "účastníkov, dokumentáciu a vizualizácie, dokumenty dodávateľov a všetky konverzácie projektu — píšete v nich v mene štúdia. "
              "Môžete pridávať súbory do sekcií projektu.\n\nOtvoríte ju tlačidlom „{menu}“ vedľa poľa na písanie. "
              "Na správu z konverzácie odpoviete potiahnutím doľava.",
        "de": "Guten Tag, {name}! Das ist die Mitarbeiter-App des Studios DUMSKAYA DESIGN. Hier finden Sie die Projekte, denen Irina Sie zugeteilt "
              "hat{now}: Beteiligte, Unterlagen und Visualisierungen, Unterlagen der Handwerker und alle Chats des Projekts — Sie schreiben darin "
              "im Namen des Studios. Sie können Dateien zu den Projektbereichen hinzufügen.\n\nÖffnen Sie sie über „{menu}“ neben dem Eingabefeld. "
              "Um auf eine Chatnachricht zu antworten, wischen Sie sie nach links."},
    "invite_assistant": {
        "ru": "Здравствуйте, {name}! {head} приглашает вас в кабинет сотрудника студии DUMSKAYA DESIGN в Telegram: проекты, на которые вас "
              "назначат, документация и разговоры с заказчиками и подрядчиками. Откройте ссылку в Telegram и нажмите кнопку внизу экрана («Старт»):\n"
              "{link}\n\nСсылка личная, для одного человека, и действует 14 дней.",
        "uk": "Добрий день, {name}! {head} запрошує вас до кабінету співробітника студії DUMSKAYA DESIGN у Telegram: проєкти, на які вас "
              "призначать, документація й розмови із замовниками та підрядниками. Відкрийте посилання в Telegram і натисніть кнопку внизу екрана («Почати»):\n"
              "{link}\n\nПосилання особисте, для однієї людини, і діє 14 днів.",
        "en": "Hello {name}! {head} invites you to the DUMSKAYA DESIGN staff app in Telegram: the projects you are assigned to, documents and chats "
              "with clients and contractors. Open the link in Telegram and tap the button at the bottom (“Start”):\n"
              "{link}\n\nThe link is personal, for one person, and is valid for 14 days.",
        "sk": "Dobrý deň, {name}! {head} vás pozýva do aplikácie pre zamestnancov štúdia DUMSKAYA DESIGN v Telegrame: projekty, na ktoré vás "
              "pridelia, dokumentácia a konverzácie s klientmi a dodávateľmi. Otvorte odkaz v Telegrame a ťuknite na tlačidlo dole („Štart“):\n"
              "{link}\n\nOdkaz je osobný, pre jednu osobu, a platí 14 dní.",
        "de": "Guten Tag, {name}! {head} lädt Sie in die Mitarbeiter-App des Studios DUMSKAYA DESIGN in Telegram ein: die Projekte, denen Sie "
              "zugeteilt werden, Unterlagen und Chats mit Kunden und Handwerkern. Öffnen Sie den Link in Telegram und tippen Sie unten auf die Schaltfläche („Starten“):\n"
              "{link}\n\nDer Link ist persönlich, für eine Person, und 14 Tage gültig."},
    "assistant_assigned": {"ru": "📁 {who} назначила вас на проект «{project}». Документация и разговоры проекта — в кабинете.",
                           "uk": "📁 {who} призначила вас на проєкт «{project}». Документація й розмови проєкту — у кабінеті.",
                           "en": "📁 {who} has assigned you to the project “{project}”. Documents and project chats are in the app.",
                           "sk": "📁 {who} vás pridelila na projekt „{project}“. Dokumentácia a konverzácie projektu sú v aplikácii.",
                           "de": "📁 {who} hat Sie dem Projekt „{project}“ zugeteilt. Unterlagen und Chats des Projekts sind in der App."},
    "assistant_hint": {"ru": "Чтобы написать в разговор проекта, ответьте на его сообщение (потяните сообщение влево) или откройте разговор в кабинете.",
                       "uk": "Щоб написати в розмову проєкту, дайте відповідь на її повідомлення (потягніть повідомлення вліво) або відкрийте розмову в кабінеті.",
                       "en": "To write in a project chat, reply to one of its messages (swipe the message to the left) or open the chat in the app.",
                       "sk": "Ak chcete napísať do konverzácie projektu, odpovedzte na jej správu (potiahnite správu doľava) alebo otvorte konverzáciu v aplikácii.",
                       "de": "Um in einen Projektchat zu schreiben, antworten Sie auf eine seiner Nachrichten (Nachricht nach links wischen) oder öffnen Sie den Chat in der App."},
    "ctx_thread": {"ru": "Разговор: {title}", "uk": "Розмова: {title}", "en": "Chat: {title}", "sk": "Konverzácia: {title}", "de": "Chat: {title}"},
}
SYM = {"EUR": "€", "USD": "$", "UAH": "₴", "PLN": "zł", "CZK": "Kč", "GBP": "£", "CHF": "CHF"}


def t(lang, key, **kw):
    """Текст бота на языке человека: русский, украинский, английский, словацкий, немецкий — здесь, остальные языки —
    deploy/i18n/<код>.json (langs.py); нет перевода — по-английски."""
    d = T[key]
    s = d.get(lang) or (pack(lang).get("bot") or {}).get(key) or d["en"]
    return s.format(**kw) if kw else s


def esc(s):
    return html.escape(str(s or ""), quote=False)


def money(x, cur="EUR", lang="ru"):
    """12 000 € / 12,000 € (по-английски) / 1 500,50 ₴."""
    x = round(float(x or 0), 2)
    whole, frac = f"{abs(x):,.2f}".split(".")
    sep, dec = (",", ".") if lang in ("en", "ga", "mt") else (" ", ",")
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

    def has_portal(self):
        return bool(getattr(self, "portal", None))

    def sync_portal_menu(self, uid):
        """Кнопка «Мой проект» слева от поля ввода — у тех, у кого есть кабинет (у студии — своя кнопка «Студия»)."""
        u = self.user(uid)
        if not u or self.is_admin(u) or not self.has_portal():
            return
        url = self.portal_url()
        if u["status"] == "active" and url and self.portal.has_cabinet(uid):
            self.api("setChatMenuButton", chat_id=uid, menu_button={"type": "web_app", "text": t(self.lang_of(uid), "menu"),
                                                                     "web_app": {"url": url}})
            self.s.put(f"pmenu:{uid}", "1")
        elif self.s.get(f"pmenu:{uid}"):
            self.api("setChatMenuButton", chat_id=uid, menu_button={"type": "commands"})
            self.s.drop(f"pmenu:{uid}")

    def portal_welcome(self, u):
        """Что это за бот — заказчику, подрядчику, работнику (на его языке)."""
        uid = u["tg_id"]
        lang = self.lang_of(uid)
        if not self.has_portal():
            return t(lang, "no_projects")
        ps = self.portal.projects_for(uid)
        name = esc(u["name"] or "")
        mine = [p for p in ps if "client" in p["roles"]]
        if mine:
            return t(lang, "welcome_client", name=name, project=esc(", ".join(self.loc(x["title"], lang) for x in mine[:3])), menu=t(lang, "menu"))

        def now_of(role):
            here = [p for p in ps if role in p["roles"]]
            return t(lang, "now", project=esc(", ".join(self.loc(x["title"], lang) for x in here[:3]))) if here else ""
        if self.portal.assistants_of(uid):                # сотрудник студии
            return t(lang, "welcome_assistant", name=name, now=now_of("assistant"), menu=t(lang, "menu"))
        heads = self.portal.my_contractors(uid)
        if heads:                                         # подрядчик или поставщик
            key = "welcome_supplier" if all(c.get("kind") == "supplier" for c in heads) else "welcome_crew"
            return t(lang, key, name=name, now=now_of("contractor"), menu=t(lang, "menu"))
        crews = self.portal.crews_of(uid)
        if crews:
            return t(lang, "welcome_worker", name=name, head=esc(crews[0]["head_name"]), menu=t(lang, "menu"))
        return t(lang, "no_projects")

    def invite_text(self, lang, kind, name, project, link):
        """Текст ссылки-приглашения. kind: client (project — проект), contractor, supplier, crew (project — имя подрядчика),
        assistant (сотрудник студии — от имени Ирины)."""
        lang = ui_lang(lang)
        if kind == "client":
            return t(lang, "invite_client", name=name, project=project, link=link)
        if kind == "crew":
            return t(lang, "invite_crew", name=name, head=project, link=link)
        if kind == "assistant":
            return t(lang, "invite_assistant", name=name, head=self.designer_name(lang), link=link)
        return t(lang, "invite_supplier" if kind == "supplier" else "invite_contractor", name=name, link=link)

    # ---------- вход по ссылке-приглашению ----------
    ROLE_OF = {"client": "client", "contractor": "crew", "crew": "worker", "assistant": "assistant"}
    RANK = {"assistant": 4, "client": 3, "crew": 2, "worker": 1}

    def join_portal(self, uid, name, username, lang_code, u, token):
        if lang_code and not self.s.get(f"tg:lang:{uid}"):
            self.s.put(f"tg:lang:{uid}", str(lang_code)[:8])
        if u and u["status"] == "active" and self.is_admin(u):
            return self.send(uid, "Это ссылка для заказчика, подрядчика или работника — по ней он попадёт в кабинет. "
                                  "Вы в студии: кабинет глазами заказчика, подрядчика или работника можно посмотреть в «Студии» — "
                                  "проект → «👁 Как видит…». Ссылка осталась действующей.")
        if not self.has_portal():
            return self.send(uid, t(self.lang_of(uid), "invite_bad"))
        inv = self.portal.invite(token)
        if inv and not lang_code and not self.s.get(f"tg:lang:{uid}"):
            self.s.put(f"tg:lang:{uid}", inv["lang"] or "ru")
        r = self.portal.use_invite(token, uid, name)
        if r and r.get("lang") and not self.s.get(f"ui:lang:{uid}"):    # язык из ссылки (его выбрала студия или подрядчик);
            self.s.put(f"ui:lang:{uid}", ui_lang(r["lang"]))             # человек сменит его сам — 🌐 в кабинете
        lang = self.lang_of(uid)
        if not r:
            return self.send(uid, t(lang, "invite_bad"))
        role = self.ROLE_OF[r["kind"]]
        if not u:
            self.s.run("INSERT INTO users(tg_id, name, username, role, status, created, updated) VALUES(?, ?, ?, ?, 'active', ?, ?)",
                       uid, name, username, role, _now(), _now())
        elif u["status"] != "active" or u["role"] in (None,) + PORTAL_ROLES:
            if u["status"] == "active" and self.RANK.get(u["role"], 0) > self.RANK[role]:
                role = u["role"]                          # и заказчик, и подрядчик — главное, что заказчик
            self.s.run("UPDATE users SET role=?, status='active', partner_id=NULL, updated=? WHERE tg_id=?", role, _now(), uid)
        if r.get("replaced"):                             # к этой записи был привязан другой Telegram — у него доступа больше нет
            self.portal_unlinked(r["replaced"])
        u = self.user(uid)
        self.set_commands(u)
        self.sync_portal_menu(uid)
        p = r["project"] or {}
        row = self.portal_row(lang, f"project={p['id']}" if p.get("id") else "")
        self.send(uid, self.portal_welcome(u), [row] if row else None)
        tgline = f"\nTelegram: {esc(name)}" + (f" (@{esc(username)})" if username else "")
        if r["kind"] == "crew":
            head = r.get("head") or {}
            pos = r["ref"].get("position") or ""
            self.notify(f"✅ <b>{esc(r['ref']['name'])}</b>{(' (' + esc(pos) + ')') if pos else ''} из бригады подрядчика "
                        f"<b>{esc(head.get('name') or '')}</b> подключился к кабинету{tgline}", roles=("designer",))
            if head.get("tg_id") and self._active(head["tg_id"]):
                hl = self.lang_of(head["tg_id"])
                hrow = self.portal_row(hl, "team=1")
                self.send(head["tg_id"], t(hl, "crew_joined_sup" if head.get("kind") == "supplier" else "crew_joined", name=esc(r["ref"]["name"])),
                          [hrow] if hrow else None)
            return
        if r["kind"] == "assistant":                      # сотрудник студии
            pos = r["ref"].get("position") or ""
            n = len(self.portal.projects_for(uid))
            self.notify(f"✅ <b>{esc(r['ref']['name'])}</b>{(' (' + esc(pos) + ')') if pos else ''} — сотрудник студии — подключился к кабинету"
                        f"{tgline}\n" + (f"Назначен на проектов: {n}." if n else "Пока ни на одном проекте: назначьте в проекте → «Сотрудники студии»."),
                        roles=("designer",))
            return
        what = "заказчик проекта «" + esc(p.get("title") or "") + "»" if r["kind"] == "client" else \
            ("поставщик" if r["ref"].get("kind") == "supplier" else "подрядчик") + \
            (" (сейчас в проекте «" + esc(p.get("title") or "") + "»)" if p.get("id") else " — проекты, куда его добавят, увидит сам")
        btn = self.studio_button("📁 Открыть проект", p.get("id")) if p.get("id") else None
        self.notify(f"✅ <b>{esc(r['ref']['name'])}</b> подключился к кабинету — {what}{tgline}",
                    roles=("designer",), rows=[btn] if btn else None)

    def portal_unlinked(self, tg_id):
        """Telegram отвязан (заказчик, подрядчик или работник): если кабинета у него больше нет — доступ к боту закрыт."""
        u = self.user(tg_id)
        if not u:
            return
        if u["role"] in PORTAL_ROLES and u["status"] == "active" and not (self.has_portal() and self.portal.has_cabinet(tg_id)):
            self.s.run("UPDATE users SET status='removed', updated=? WHERE tg_id=?", _now(), tg_id)
            self.send(tg_id, t(self.lang_of(tg_id), "closed"))
        self.sync_portal_menu(tg_id)

    def portal_relinked(self, tg_id):
        """Заказчика или подрядчика с привязанным Telegram снова добавили в проект — открыть доступ к боту обратно
        (если его закрыли, когда проектов не осталось; закрытое студией вручную — тоже, раз студия добавила снова)."""
        u = self.user(tg_id)
        if u and u["role"] in PORTAL_ROLES and u["status"] == "removed" and self.portal.has_cabinet(tg_id):
            self.s.run("UPDATE users SET status='active', updated=? WHERE tg_id=?", _now(), tg_id)
            row = self.portal_row(self.lang_of(tg_id))
            self.send(tg_id, self.portal_welcome(self.user(tg_id)), [row] if row else None)
        self.sync_portal_menu(tg_id)

    # ---------- сообщения в чате бота ----------
    def _map_put(self, chat_id, message_id, pid, tid):
        if message_id:
            self.s.put(f"chatmap:{chat_id}:{message_id}", json.dumps({"p": int(pid), "th": int(tid), "t": int(time.time())}))

    def _map_get(self, chat_id, message_id):
        """Разговор, на сообщение которого отвечают свайпом (или None)."""
        try:
            d = json.loads(self.s.get(f"chatmap:{chat_id}:{message_id}") or "{}")
        except (ValueError, TypeError):
            return None
        th = int(d.get("th") or 0)
        if not th and d.get("p") and self.has_portal():          # ответ на сообщение первой версии — переписка с заказчиками
            t0 = self.crm.one("SELECT id FROM threads WHERE project_id=? AND kind='client'", int(d["p"]))
            th = t0["id"] if t0 else 0
        return self.portal.thread(th) if th and self.has_portal() else None

    def chat_reply(self, u, m):
        """Ответ студии свайпом на сообщение разговора — в этот разговор (в разговоре заказчика с подрядчиком студия так вступает)."""
        r = m.get("reply_to_message") or {}
        th = self._map_get(u["tg_id"], r.get("message_id")) if r else None
        if not th:
            return False
        v = self.portal.viewer(u["tg_id"], th["project_id"], designer=True)
        self._chat_in(u, th, (m.get("text") or m.get("caption") or "").strip(), self.file_of(m), v)
        return True

    def portal_message(self, u, m, text, cmd):
        """Заказчик, подрядчик или работник пишет в чат бота. Ответ свайпом — в тот разговор; иначе — в свой разговор со
        студией (один проект — сразу, несколько — спросить, к какому)."""
        uid, lang = u["tg_id"], self.lang_of(u["tg_id"])
        if not self.has_portal():
            return
        if cmd:                                           # /start, /help и любые команды — что это за бот
            row = self.portal_row(lang)
            return self.send(uid, self.portal_welcome(u), [row] if row and self.portal.has_cabinet(uid) else None)
        f = self.file_of(m)
        body = (m.get("text") or m.get("caption") or "").strip()
        if not body and not f:
            return
        r = m.get("reply_to_message") or {}
        th = self._map_get(uid, r.get("message_id")) if r else None
        if th:
            v = self.portal.viewer(uid, th["project_id"])
            acc = self.portal.access(v, th)
            if acc == "write":
                return self._chat_in(u, th, body, f, v)
            if acc == "read":
                return self.send(uid, t(lang, "read_only"))
        opts = self.portal.default_threads(uid)
        if not opts and self.portal.assistants_of(uid):  # сотрудник студии пишет в разговоры ответом свайпом или в кабинете
            row = self.portal_row(lang)
            return self.send(uid, t(lang, "assistant_hint"), [row] if row else None)
        if not opts:
            return self.send(uid, t(lang, "no_projects"))
        if len(opts) == 1:
            p, th = opts[0]
            return self._chat_in(u, th, body, f, self.portal.viewer(uid, p["id"]))
        self.s.put(f"pchat:{uid}", json.dumps({"text": body, "file": f, "ts": time.time()}, ensure_ascii=False))
        return self.send(uid, t(lang, "pick"), [[(self.loc(p["title"], lang)[:60], f"pp:{p['id']}")] for p, _ in opts[:8]])

    def _chat_in(self, u, th, text, f, v):
        """Сообщение из чата бота → в разговор (вложение — в файлы разговора) → остальным участникам."""
        uid = u["tg_id"]
        lang = "ru" if v["studio"] else self.lang_of(uid)
        fid = None
        if f:
            if f.get("size") and f["size"] > CHAT_FILE_MAX:
                return self.send(uid, t(lang, "too_big"))
            try:
                with self._download(f["id"]) as r:
                    size = int(r.headers.get("Content-Length") or f["size"] or 0)
                    rec = self.crm.add_file(th["project_id"], "chat", f["name"], r, size, f["mime"], u["name"] or str(uid),
                                            tg_file_id=f"{f['kind']}:{f['id']}")
                fid = rec["id"]
            except Exception as e:  # noqa: BLE001
                self.log(f"переписка: файл не сохранён: {type(e).__name__}: {e}")
                if not text:
                    return self.send(uid, "⚠️ " + esc(str(e))[:300])
        try:
            kind, author = self.portal.author(v, th)
            msg = self.portal.post(th["id"], kind, uid, author, text, fid)
        except CrmError as e:
            return self.send(uid, "⚠️ " + esc(e))
        threading.Thread(target=self.chat_fanout, args=(msg["id"],), kwargs={"confirm_to": uid}, daemon=True).start()

    # ---------- рассылка сообщения разговора ----------
    def _thread_bits(self, th):
        """Подрядчик и работник разговора — для подписей."""
        c = self.crm.one("""SELECT c.name, c.kind, COALESCE(l.trade, c.trade) AS trade FROM contractors c
                            LEFT JOIN project_contractors l ON l.contractor_id=c.id AND l.project_id=? WHERE c.id=?""",
                         th["project_id"], th["contractor_id"] or 0) or {}
        w = self.crm.one("SELECT w.name, w.position, c.name AS head FROM crew w JOIN contractors c ON c.id=w.contractor_id WHERE w.id=?",
                         th["crew_id"] or 0) or {}
        return c, w

    def _ctx_ru(self, th, m):
        """Чей это разговор — подпись для студии (и наблюдателя), по-русски."""
        k, a = th["kind"], m["author_kind"]
        if a == "assistant":
            a = "studio"                                  # сотрудник студии пишет от студии
        c, w = self._thread_bits(th)
        cname = (c.get("name") or "") + (f" ({c['trade']})" if c.get("trade") else "")
        if k == "pc":
            line = ("Заказчик → подрядчику " + cname if a == "client" else "Подрядчик → заказчику" if a == "contractor"
                    else "В разговоре заказчика с подрядчиком " + cname)
            if not th["studio_joined"]:
                line += "\nВы видите, но не участвуете — пока не ответите (потяните сообщение влево)."
            return line
        if k == "org":
            return ("Студия → " + ("поставщику " if c.get("kind") == "supplier" else "подрядчику ") if a == "studio"
                    else "Поставщик " if c.get("kind") == "supplier" else "Подрядчик ") + cname
        if k == "worker":
            who = (w.get("name") or "") + (f" ({w['position']})" if w.get("position") else "") + (f", бригада {w['head']}" if w.get("head") else "")
            return ("Студия → " if a == "studio" else "Работник ") + who
        if k == "group":
            return f"Группа «{th['title'] or ''}»"
        return "Студия → заказчикам" if a == "studio" else ""

    DEFAULT_KIND = {"client": "client", "contractor": "org", "crew": "worker"}

    def _thread_name(self, th, lang):
        """Название разговора для сотрудника студии (на его языке): кто в нём."""
        k = th["kind"]
        c, w = self._thread_bits(th)
        clients = ", ".join(x["name"] for x in self.crm.project_people(th["project_id"])[:3])
        if k == "client":
            return clients or t(lang, "role_client")
        if k == "pc":
            return (clients or t(lang, "role_client")) + " ↔ " + (c.get("name") or "")
        if k == "org":
            return (c.get("name") or "") + (f" ({self.loc(c['trade'], lang)})" if c.get("trade") else "")
        if k == "worker":
            return (w.get("name") or "") + (f" ({w['position']})" if w.get("position") else "")
        return th["title"] or ""

    def chat_fanout(self, mid, confirm_to=None):
        m = self.portal.message(mid)
        th = self.portal.thread(m["thread_id"]) if m else None
        if not th:
            return
        pid = m["project_id"]
        p = self.crm.one("SELECT id, title FROM projects WHERE id=?", pid) or {"id": pid, "title": ""}
        r = self.portal.recipients(th["id"], m["author_tg"], m["author_kind"])
        rec = []                                          # (tg, язык, кто, имя, со звуком)
        if r["studio"]:
            rec += [(d["tg_id"], "ru", "studio", d["name"] or "", r["studio"]["loud"]) for d in self.active(("designer",))]
        for x in r["people"]:
            if self._active(x["tg"]):
                rec.append((x["tg"], "ru" if x["who"] == "observer" else self.lang_of(x["tg"]), x["who"], x["name"], x["loud"]))
        text = m["text"] or ""
        tr, src = {}, None
        if text and self.can_translate():
            for lang in sorted({x[1] for x in rec}):
                try:
                    res = translate_text(text, lang)
                except Exception as e:  # noqa: BLE001
                    self.log(f"перевод переписки ({lang}): ошибка {type(e).__name__}: {e}")
                    res = None
                if res:
                    src, tr[lang] = res
                    self.portal.set_translation(mid, lang, res[1], res[0])
        f = self.crm.one("SELECT * FROM files WHERE id=?", m["file_id"]) if m["file_id"] else None
        c, w = self._thread_bits(th)
        delivered, failed = [], []
        for tg, lang, who, name, loud in rec:
            if who in ("studio", "observer"):
                ctx = self._ctx_ru(th, m)
                author = STUDIO["designer"]["ru"] if m["author_kind"] == "studio" else \
                    m["author_name"] + " (сотрудник студии)" if m["author_kind"] == "assistant" else m["author_name"]
                head = ("🧪 " if who == "observer" else "💬 ") + f"<b>{esc(author)}</b> · «{esc(p['title'])}»" + (f"\n<i>{esc(ctx)}</i>" if ctx else "")
                body = esc(text)
                if tr.get("ru"):
                    body += f"\n\n<i>Перевод на русский{(' ' + esc(lang_from(src))) if src else ''}:</i>\n{esc(tr['ru'])}"
                if who == "studio":
                    body += "\n\n<i>↩︎ Ответить: потяните сообщение влево</i>"
                    rows = [self.studio_button("💬 Открыть разговор", query=f"project={pid}&thread={th['id']}")]
                else:
                    rows = [self.portal_row("ru", f"project={pid}&thread={th['id']}", "open_chat")]
            else:
                if m["author_kind"] == "studio":
                    author = self.designer_name(lang)
                elif m["author_kind"] == "assistant":
                    author = m["author_name"] + " · " + STUDIO["name"]
                elif m["author_kind"] == "contractor":
                    author = m["author_name"] + (f" · {self.loc(c['trade'], lang)}" if th["kind"] == "pc" and who == "client" and c.get("trade") else "")
                elif m["author_kind"] == "client" and who != "client":
                    author = m["author_name"] + " · " + t(lang, "role_client")
                else:
                    author = m["author_name"]
                ctx = ""
                if who == "assistant":                    # сотруднику студии — в каком разговоре
                    ctx = t(lang, "ctx_thread", title=self._thread_name(th, lang))
                elif th["kind"] == "group":
                    ctx = t(lang, "ctx_group", title=th["title"] or "")
                elif th["kind"] == "worker" and who == "contractor":
                    ctx = t(lang, "ctx_watch", name=w.get("name") or "")
                if th["kind"] == "group" and not loud and who != "assistant":
                    ctx = "👁 " + ctx
                head = f"💬 <b>{esc(author)}</b> · «{esc(self.loc(p['title'], lang))}»" + (f"\n<i>{esc(ctx)}</i>" if ctx else "")
                body = esc(tr.get(lang) or text)
                if tr.get(lang):
                    body += f"\n\n<i>{t(lang, 'auto_tr')}</i>"
                if loud and th["kind"] != self.DEFAULT_KIND.get(who):     # не «свой» разговор — ответ только свайпом
                    body += f"\n\n<i>{t(lang, 'reply_hint')}</i>"
                rows = [self.portal_row(lang, f"project={pid}&thread={th['id']}", "open_chat")]
            rows = [x for x in rows if x] or None
            ok, why, msg_id = self._send_chat(tg, head, body.strip(), f, rows, silent=not loud)
            if ok:
                if who != "observer":
                    delivered.append(name)
                    self._map_put(tg, msg_id, pid, th["id"])
            elif who != "observer":
                failed.append((name, why))
        if confirm_to:
            u = self.user(confirm_to)
            to = [x for x in rec if x[2] != "observer"]
            if u and self.is_admin(u):
                line = ("✓ Отправлено: " + ", ".join(esc(x) for x in delivered)) if delivered else "⚠️ Никому не доставлено"
                if any(tr.get(x[1]) for x in to if x[2] != "studio"):
                    line += " (с переводом)"
                if failed:
                    line += "\n" + "\n".join(f"⚠️ {esc(n)} — не доставлено: {esc(self.why(w_))}" for n, w_ in failed)
                if not to:
                    line = "⚠️ Здесь пока никто не подключён к боту — сообщение сохранено в разговоре, но никому не отправлено."
                self.send(confirm_to, line)
            elif u:
                self.send(confirm_to, t(self.lang_of(confirm_to), "sent", project=esc(self.loc(p["title"], self.lang_of(confirm_to)))))
        elif m["author_kind"] in ("studio", "assistant") and failed:
            self.notify("⚠️ Сообщение в разговоре «" + esc(p["title"]) + "» не доставлено:\n" +
                        "\n".join(f"{esc(n)} — {esc(self.why(w_))}" for n, w_ in failed), roles=("designer",))

    @staticmethod
    def why(desc):
        try:
            from bot import why_failed
            return why_failed(desc)
        except ImportError:
            return desc

    def _send_chat(self, chat_id, head, body, f, rows, silent=False):
        """Сообщение разговора в Telegram: текст или файл с подписью. (доставлено, причина, номер сообщения)."""
        text = head + ("\n" + body if body else "")
        if not f:
            p = {"chat_id": chat_id, "text": text[:4090], "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
            if rows:
                p["reply_markup"] = self.kb(rows)
            if silent:
                p["disable_notification"] = True
            r = self.api("sendMessage", **p)
            return bool(r.get("ok")), str(r.get("description") or ""), (r.get("result") or {}).get("message_id")
        caption = text if len(text) <= 1000 else head
        ok, why, mid = self.send_file_r(chat_id, f, self.crm.file_path(f["id"], "o")[0], caption=caption, rows=rows, silent=silent)
        if ok and caption != text:
            self.send_r(chat_id, text[:4090], disable_notification=True)
        return ok, why, mid

    # ---------- кнопки в чате ----------
    def portal_callback(self, who, msg, parts):
        uid, lang = who["tg_id"], self.lang_of(who["tg_id"])
        act = parts[0]
        if not self.has_portal():
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
        if act == "pp":                                     # к какому проекту сообщение (несколько проектов)
            pid = int(parts[1])
            try:
                d = json.loads(self.s.get(f"pchat:{uid}") or "{}")
            except ValueError:
                d = {}
            self.s.drop(f"pchat:{uid}")
            th = next((x for p, x in self.portal.default_threads(uid) if p["id"] == pid), None)
            if not d or time.time() - d.get("ts", 0) > 1800 or not th:
                return self.edit(msg, t(lang, "stage_gone"))
            p = self.crm.one("SELECT title FROM projects WHERE id=?", pid) or {}
            self.edit(msg, "→ «" + esc(self.loc(p.get("title") or "", lang)) + "»")
            self._chat_in(who, th, d.get("text") or "", d.get("file"), self.portal.viewer(uid, pid))

    # ---------- события из кабинета и «Студии» ----------
    def _stage_info(self, sid):
        st = self.crm.one("SELECT * FROM stages WHERE id=?", int(sid))
        if not st:
            return None
        k = self.crm.one("""SELECT l.trade AS link_trade, c.name, c.trade, c.tg_id, c.kind FROM project_contractors l
                            JOIN contractors c ON c.id=l.contractor_id WHERE l.id=?""", st["link_id"]) or {}
        p = self.crm.one("SELECT id, title, status FROM projects WHERE id=?", st["project_id"]) or {}
        return st, k, p

    def _stage_text(self, sid, lang):
        info = self._stage_info(sid)
        if not info:
            return ""
        st, k, p = info
        trade = k.get("link_trade") or k.get("trade") or ""
        return t(lang, "supply_ask" if k.get("kind") == "supplier" else "stage_ask", project=esc(self.loc(p.get("title"), lang)), who=esc(k.get("name", "")) + (f" ({esc(self.loc(trade, lang))})" if trade else ""),
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
                    sup = k.get("kind") == "supplier"
                    self.notify(f"🧾 <b>{'Поставщик' if sup else 'Подрядчик'} {esc(k.get('name'))}</b> внёс сумму {'поставки' if sup else 'работ'} · «{esc(p.get('title'))}»\n{line}\n\n"
                                + ("Заказчику отправлено на подтверждение." if asked else
                                   "Заказчик не подключён к кабинету — подтвердить некому. Пригласите заказчика или проверьте сумму сами.")
                                + ("\n\nПроект завершён — вернуть в работу: «Студия» → проект → «↺ Вернуть в работу»." if p.get("status") == "done" else ""),
                                roles=("designer",), rows=[studio] if studio else None)
                elif k.get("tg_id") and self._active(k["tg_id"]):
                    lang = self.lang_of(k["tg_id"])
                    row = self.portal_row(lang, f"project={pid}")
                    self.send(k["tg_id"], t(lang, "c_by_studio_sup" if k.get("kind") == "supplier" else "c_by_studio",
                                            project=esc(self.loc(p.get("title"), lang)), title=esc(self.loc(st["title"], lang) or "—"),
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
        if kind == "link_new":                              # подрядчика добавили в проект
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
            return
        if kind == "crew_assigned":                         # работника отметили на объекте — ему сообщение и кнопка
            w = self.crm.one("SELECT * FROM crew WHERE id=? AND removed IS NULL", int(kw.get("crew_id") or 0))
            if not w or not w["tg_id"]:
                return
            self.portal_relinked(w["tg_id"])
            if not self._active(w["tg_id"]):
                return
            p = self.crm.one("SELECT id, title FROM projects WHERE id=?", int(kw.get("project_id") or 0)) or {}
            lang = self.lang_of(w["tg_id"])
            row = self.portal_row(lang, f"project={p.get('id')}")
            self.sync_portal_menu(w["tg_id"])
            self.send(w["tg_id"], t(lang, "crew_assigned", project=esc(self.loc(p.get("title") or "", lang))), [row] if row else None)
            return
        if kind == "assistant_assigned":                    # сотрудника студии назначили на проект — ему сообщение и кнопка
            a = self.crm.one("SELECT * FROM assistants WHERE id=? AND removed IS NULL", int(kw.get("assistant_id") or 0))
            if not a or not a["tg_id"]:
                return
            self.portal_relinked(a["tg_id"])
            if not self._active(a["tg_id"]):
                return
            p = self.crm.one("SELECT id, title FROM projects WHERE id=?", int(kw.get("project_id") or 0)) or {}
            lang = self.lang_of(a["tg_id"])
            row = self.portal_row(lang, f"project={p.get('id')}")
            self.sync_portal_menu(a["tg_id"])
            self.send(a["tg_id"], t(lang, "assistant_assigned", who=esc(self.designer_name(lang)), project=esc(self.loc(p.get("title") or "", lang))),
                      [row] if row else None)
            return
        if kind == "group_new":                             # Ирина собрала группу — участникам сообщение на их языке
            th = self.portal.thread(kw.get("thread_id"))
            if not th:
                return
            p = self.crm.one("SELECT id, title FROM projects WHERE id=?", th["project_id"]) or {}
            names, tgs = [], []
            for m in self.portal.members(th["id"]):
                if m["kind"] == "contractor":
                    x = self.crm.one("SELECT name, tg_id FROM contractors WHERE id=?", m["ref_id"]) or {}
                else:
                    x = self.crm.one("SELECT name, tg_id FROM crew WHERE id=? AND removed IS NULL", m["ref_id"]) or {}
                if x.get("name"):
                    names.append(x["name"])
                if x.get("tg_id") and (not kw.get("only") or m in kw["only"]):
                    tgs.append(int(x["tg_id"]))
            for tg in dict.fromkeys(tgs):
                if not self._active(tg):
                    continue
                lang = self.lang_of(tg)
                row = self.portal_row(lang, f"project={p.get('id')}&thread={th['id']}", "open_chat")
                ok, _, mid = self._send_chat(tg, t(lang, "group_new", who=esc(self.designer_name(lang)), title=esc(th["title"] or ""),
                                                   project=esc(self.loc(p.get("title") or "", lang)), members=esc(", ".join(names))),
                                             "", None, [row] if row else None)
                if ok:
                    self._map_put(tg, mid, th["project_id"], th["id"])     # ответ свайпом на это сообщение — в группу
            return
        if kind == "doc_new":                               # документ подрядчика или работника: студии, подрядчику, заказчику
            f = self.crm.one("SELECT * FROM files WHERE id=?", int(kw.get("file_id") or 0))
            if not f:
                return
            p = self.crm.one("SELECT id, title FROM projects WHERE id=?", f["project_id"]) or {}
            studio = self.studio_button("📁 Открыть проект", p.get("id"))
            if f["owner_assistant"]:                        # файл сотрудника студии — Ирине (заказчику — как решили при загрузке)
                a = self.crm.one("SELECT name, position FROM assistants WHERE id=?", f["owner_assistant"]) or {}
                cat = dict(FILE_CATS).get(f["category"], f["category"])
                self.notify(f"📎 <b>Новый файл</b> · «{esc(p.get('title') or '')}» → «{esc(cat)}»\n{esc(a.get('name') or '')}"
                            f"{(' (' + esc(a['position']) + ')') if a.get('position') else ''}, сотрудник студии: {esc(f['title'] or f['name'] or '')}"
                            f"\n<i>Видят: {esc(self.portal.audience(f))}</i>"
                            + ("\nЗаказчику не видно — открыть можно в «Студии»: проект → файл → «Кто видит»." if f["see_client"] == 0 else ""),
                            roles=("designer",), rows=[studio] if studio else None)
                return
            head = self.crm.one("SELECT id, name, trade, tg_id FROM contractors WHERE id=?", f["owner_contractor"] or 0) or {}
            wk = self.crm.one("SELECT name, position, tg_id FROM crew WHERE id=?", f["owner_crew"] or 0) if f["owner_crew"] else None
            who = (wk["name"] + (f" ({wk['position']})" if wk.get("position") else "") + f", бригада {head.get('name') or ''}") if wk \
                else (head.get("name") or "") + (f" ({head['trade']})" if head.get("trade") else "")
            title = f["title"] or f["name"] or ""
            aud = self.portal.audience(f)
            self.notify(f"📎 <b>Новый документ</b> · «{esc(p.get('title') or '')}»\n{esc(who)}: {esc(title)}\n<i>Видят: {esc(aud)}</i>",
                        roles=("designer",), rows=[studio] if studio else None)
            name = wk["name"] if wk else head.get("name") or ""
            targets = []
            if wk and head.get("tg_id") and head["tg_id"] != wk.get("tg_id"):
                targets.append(int(head["tg_id"]))
            if f["vis"] == "client" or f["see_client"] == 1:
                targets += self._client_tgs(f["project_id"])
            for tg in dict.fromkeys(targets):
                if not self._active(tg):
                    continue
                lang = self.lang_of(tg)
                row = self.portal_row(lang, f"project={p.get('id')}&tab=docs")
                self.send(tg, t(lang, "doc_new", project=esc(self.loc(p.get("title") or "", lang)), who=esc(name), title=esc(title)),
                          [row] if row else None)
            return

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
