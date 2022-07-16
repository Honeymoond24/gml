import sys
import logging
from pyrogram import Client, filters
import re
import requests
import json
from configparser import ConfigParser

cfg = ConfigParser()
cfg.read('config.ini')

logging.basicConfig(filename='gml_fs_to_poster.log', encoding='utf-8',
                    format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S')
logging.warning(sys.version)
# Telegram account id hash
# GML
api_id = cfg.get('pyrogram', 'api_id')
api_hash = cfg.get('pyrogram', 'api_hash')
fs_order_notifications_bot_id = cfg.get('pyrogram', 'fs_order_notifications_bot_id')
admin_id = cfg.get('pyrogram', 'admin_id')
app = Client("my_account", api_id=api_id, api_hash=api_hash)
print("Pyrogram подключен")
# Poster POS API
poster_pos_token = cfg.get('poster', 'poster_pos_token')  # GML
url_createIncomingOrder = "https://joinposter.com/api/incomingOrders.createIncomingOrder?token=" + poster_pos_token

exception_products = {
    "Доп. порция": [
        "Имбирь",
        "Васаби",
        "Соевый соус"
    ],
    "Соуса": [
        "Соус Цезарь",
        "Кетчуп",
        "Майонез"
    ],
    "Сок": [
        "Сок Добрый"
    ],
    "Bon Aqua": [
        "Вода Bon Aqua негаз.",
        "Вода Bon Aqua газ.",
    ]
}
categories_exceptions = ["Сеты", "Комбо"]


# Получить имя продукта из запроса
def product_id_by_name(js, name):
    for product in js['response']:
        if product['product_name'].lower().replace('ё', 'е').strip() == name.lower().replace('ё', 'е').strip():
            return product['product_id']


def product_modification_get(js, name, modification_name, modification_count):
    for product in js['response']:
        if product['product_name'].lower().replace('ё', 'е').strip() == name.lower().replace('ё', 'е').strip():
            if product['category_name'] in categories_exceptions:
                modifications_list = []
                for group_modification in product['group_modifications']:
                    for modification in group_modification['modifications']:
                        modifications_list.append(modification['dish_modification_id'])
                modifications_output = []
                for modification in modifications_list:
                    modifications_output.append({
                        "m": modification,
                        "a": 1
                    })
                return modifications_output
            else:
                try:
                    for group_modification in product['group_modifications']:
                        for modification in group_modification["modifications"]:
                            if modification["name"].lower().replace('ё', 'е').strip() \
                                    == modification_name.lower().replace('ё', 'е').strip():
                                return [{"m": modification["dish_modification_id"], "a": 1}]
                except KeyError:
                    try:
                        for modification in product["modifications"]:
                            if modification["modificator_name"].lower().replace('ё', 'е').strip() \
                                    == modification_name.lower().replace('ё', 'е').strip():
                                return modification["modificator_id"]
                    except KeyError:
                        return None


def sause_id_by_name(js, name):
    for product in js['response']:
        if product['product_name'] == 'Соуса':
            for modification in product["group_modifications"][0]["modifications"]:
                if modification['name'].lower().replace('ё', 'е').strip() == name.lower().replace('ё', 'е').strip():
                    return modification["dish_modification_id"]


def additional_modification_id_by_name(js, m_name):
    for product in js['response']:
        if product['product_name'] == "Доп. порция":
            for modification in product["group_modifications"][0]["modifications"]:
                if modification["name"].lower().replace('ё', 'е').strip() == m_name.lower().replace('ё', 'е').strip():
                    return modification["dish_modification_id"]


def get_additional_modifications(js, product):  # Данные из "product_name": "Доп. порция", "product_id": "272"
    modifications_input = re.split('             \d+\) ',
                                   product.split('Дополнительные модификаторы\n')[1]
                                   .split('\nИтого модификаторов на сумму')[0])[1:]
    modifications_output = []
    for m in modifications_input:
        m_name = m.split(': ')[0]
        m_count = m.split(' = ')[0].split(' x ')[1]
        m_data = {
            "m": additional_modification_id_by_name(js, m_name),
            "a": int(m_count)
        }
        modifications_output.append(m_data)
    return modifications_output


@app.on_message(filters.all)
async def get_message_text(client, message):
    # if message.from_user.id != test_bot_id and message.from_user.id != test_account_id:
    if message.from_user.id != fs_order_notifications_bot_id and message.from_user.id != admin_id:
        print(message.from_user.id, 'Чужое сообщение:', message.text)
        logging.warning(str(message.from_user.id) + ' Чужое сообщение: ' + str(message.text))
        return 0
    logging.warning('\n' + str(message) + '\n')
    order = message.text
    print(order)
    logging.warning(str(order))
    url = 'https://joinposter.com/api/menu.getProducts?token=' + poster_pos_token
    r = requests.get(url=url, data={})  # Запрос всех продуктов из Poster POS
    # Добавление продуктов в список для отправки онлайн-заказа
    products = []
    print(re.split('\n\d+\) ', order.split('Список товаров:')[1].rsplit('Расчет: ', 1)[0])[1:])
    logging.warning(str(re.split('\n\d+\) ', order.split('Список товаров:')[1].rsplit('Расчет: ', 1)[0])[1:]))
    # Исключение для Доп. порция
    is_dop_portion = False
    dop_portion = {"product_id": 272, "count": 1, "modification": []}  # Доп. порция
    are_sauses = False
    sauses = {"product_id": 155, "count": 1, "modification": []}  # Соуса
    is_bonaqua = False
    bonaqua = {"product_id": 450, "count": 1, "modification": []}  # Bon Aqua
    products_input = re.split('\n\d+\) ', order.split('Список товаров:')[1].rsplit('Расчет: ', 1)[0])[1:]
    for p_id, product in enumerate(products_input):
        product_parsed_data = {}
        product_lines = product.split('\n')
        for line in product_lines:
            if ':' in line:
                product_parsed_data[line.split(':', 1)[0].strip()] = line.split(':', 1)[1].strip()
        print("product_parsed_data", product_parsed_data)  # Словарь полей продукта, найденных по разделителю ":"
        logging.warning("product_parsed_data " + str(product_parsed_data))
        print("product", product)  # Сам продукт
        logging.warning("product " + str(product))
        if product_parsed_data['Стоимость'] == "Подарок":
            if p_id == len(products_input) - 1:
                if is_dop_portion:
                    products.append(dop_portion)
                if are_sauses:
                    products.append(sauses)
                if is_bonaqua:
                    products.append(bonaqua)
            continue
        product_data = {}
        product_name = product.split('\n')[0].split(' - ')[0]
        product_id = product_id_by_name(r.json(), product_name)
        product_modification = product.split('\n')[0].split(' - ')[1].split(' Итого:')[0].replace('г.', 'гр')
        to_continue = False
        for product_collission_check_index, product_collission_check in enumerate(products):
            if product_collission_check["product_id"] == product_id:
                if "modification" in products[product_collission_check_index]:
                    modifications_list = products[product_collission_check_index]["modification"]
                    product_modification_check = product_modification_get(r.json(), product.split('\n')[0]
                                                                          .split(' - ')[0], product_modification,
                                                                          product_parsed_data['Количество'])
                    if product_modification_check is not None:
                        modifications_list.extend(product_modification_check)
                    products[product_collission_check_index]["modification"] = modifications_list
                to_continue = True
                break
        if to_continue:
            continue
        if product_id is not None:
            product_data["product_id"] = product_id
            product_data["count"] = product_parsed_data['Количество']
            product_modification_check = product_modification_get(r.json(), product.split('\n')[0]
                                                                  .split(' - ')[0],
                                                                  product_modification,
                                                                  product_parsed_data['Количество'])
            if product_modification_check is not None:
                if isinstance(product_modification_check, list):
                    product_data["modification"] = product_modification_check
                else:
                    product_data["modificator_id"] = product_modification_check
            if "Дополнительные модификаторы" in product:
                is_dop_portion = True
                modifiers = get_additional_modifications(r.json(), product)
                for modifier in modifiers:
                    for index, modification in enumerate(dop_portion["modification"]):
                        if modifier["m"] == modification["m"]:
                            dop_portion["modification"][index]["a"] += modifier["a"]
                            modifiers = [modifier for modifier in modifiers if not (modifier['m'] == modification["m"])]
                dop_portion["modification"].extend(modifiers)
                print("dop_portion", dop_portion)
                logging.warning("dop_portion " + str(dop_portion))
            print("Название продукта в базе фудсоула: ")
            print(product_name)
            logging.warning("Название продукта в базе фудсоула: " + product_name)
            products.append(product_data)
        else:
            if product_name == "Вода Bon Aqua газ." or product_name == "Вода Bon Aqua негаз.":
                is_bonaqua = True
                m_id = None
                if product_name == "Вода Bon Aqua газ.":
                    if product_modification == "1 л.":
                        m_id = "704"
                    elif product_modification == "0.5 л.":
                        m_id = "705"
                elif product_name == "Вода Bon Aqua негаз.":
                    if product_modification == "1 л.":
                        m_id = "706"
                    elif product_modification == "0.5 л.":
                        m_id = "707"
                modification_bonaqua = {"m": m_id, "a": int(product_parsed_data['Количество'])}
                bonaqua["modification"].append(modification_bonaqua)
            if product_name.lower() in [sause.lower() for sause in exception_products['Соуса']]:
                are_sauses = True
                modification_sause = {
                    "m": sause_id_by_name(r.json(), product_name.lower()),
                    "a": int(product_parsed_data['Количество'])
                }
                sauses["modification"].append(modification_sause)
            if product_name == "Сок Добрый":
                dobriy_sok = {
                    'product_id': '476',
                    'count': product_parsed_data['Количество'],
                    'modification': '768'
                }
                products.append(dobriy_sok)
        if p_id == len(products_input) - 1:
            if is_dop_portion:
                products.append(dop_portion)
            if are_sauses:
                products.append(sauses)
            if is_bonaqua:
                products.append(bonaqua)
    parse_data = {}
    lines = order.split('\n')
    for line in lines:
        if ':' in line:
            parse_data[line.split(':', 1)[0].strip()] = line.split(':', 1)[1].strip()
    payment_method = parse_data['Способ оплаты']
    phone = parse_data['Телефон'].replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
    name = parse_data['Имя']
    first_name = name.split(' ')[0] if ' ' in name else name
    last_name = name.split(' ')[1] if ' ' in name else ''
    service_mode = parse_data['Способ доставки']
    service_mode = 3 if service_mode == 'Курьером' else 2
    # Комментарий
    comment = 'Количество персон: ' + parse_data['Количество персон'] + '; '
    comment += 'Способ оплаты: ' + payment_method + '; '
    if payment_method == 'Наличными':
        try:
            if int(parse_data['Сдача с']) - int(parse_data['Итого'].split(' тг')[0]) == 0:
                comment += 'Без сдачи; '
            else:
                comment += 'Сдача с: ' + parse_data['Сдача с'] + ' тг; '
                comment += 'Сдача: ' + str(int(parse_data['Сдача с']) -
                                           int(parse_data['Итого'].split(' тг')[0])) + ' тг; '
            print(str(int(order.split('Итого: ')[-1].split(' тг')[0])))
            logging.warning(str(int(order.split('Итого: ')[-1].split(' тг')[0])))
        except KeyError:
            print("KeyError где-то в сдаче")
            logging.warning("KeyError где-то в сдаче")
    if 'Оплата бонусами' in parse_data:
        comment += 'Оплата бонусами: ' + parse_data['Оплата бонусами'].lower().split(' ฿')[0] + '; '
    if 'Комментарий: ' in order:
        comment += 'Комментарий клиента: ' + parse_data['Комментарий'] + '; '
    data = {
        "spot_id": 1,
        "phone": phone,
        "products": products,
        "first_name": first_name,
        "last_name": last_name,
        "service_mode": service_mode,
        "comment": comment,
    }
    # Если доставка курьером
    if service_mode == 3:
        if 'Доплата за доставку' in order.split('Количество персон: ')[1].split('\n', 1)[1]:
            delivery_price = int(order.split('Количество персон: ')[1].split('\n', 1)[1]
                                 .split('Доплата за доставку ')[1].split('\n')[0].split(' тг')[0]) * 100
            data["delivery_price"] = delivery_price
        address1 = order.split('Улица: ')[1].split('\n')[0] + ' ' + order.split('Дом: ')[1].split('\n')[0]
        address2 = ''
        if 'Корпус: ' in order.split('Адрес доставки')[1].split('Количество персон: ')[0]:
            address2 += 'Корпус: ' + order.split('Корпус: ')[1].split('\n')[0] + '; '
        if 'Подъезд: ' in order.split('Адрес доставки')[1].split('Количество персон: ')[0]:
            address2 += 'Подъезд: ' + order.split('Подъезд: ')[1].split('\n')[0] + '; '
        if 'Квартира: ' in order.split('Адрес доставки')[1].split('Количество персон: ')[0]:
            address2 += 'Квартира: ' + order.split('Квартира: ')[1].split('\n')[0] + '; '
        # if 'Комментарий: ' in order:
        #     address2 += 'Комментарий клиента: ' + parse_data['Комментарий'] + '; '
        client_address = {
            "address1": address1,
            "address2": address2,
        }
        data["client_address"] = client_address
        if 'Доставить к: ' in order:
            data["comment"] += 'Доставить к: ' + parse_data['Доставить к'] + '; '
            # 13:40 27/02/2022
            # YYYY-MM-DD hh:mm:ss
            datetime = parse_data['Доставить к'].split(' ')
            date = datetime[1].split('/')
            data["delivery_time"] = f'{date[2]}-{date[1]}-{date[0]} {datetime[0]}:00'
    # Промо код, акции
    if 'Промо код: ' in order:
        url_getPromotions = "https://joinposter.com/api/clients.getPromotions?token=" + poster_pos_token
        promotions = requests.get(url=url_getPromotions, data={})
        promotion_input = order.split('\n             Промо код: ')[1].split('\n')[0].lower()
        result_products = []
        involved_products = []
        promotion_id = None
        for promotion in promotions.json()['response']:
            if promotion['name'].lower() == promotion_input.lower():
                promotion_id = promotion['promotion_id']
                if len(promotion['params']['bonus_products']) != 0:
                    for bonus_product in promotion['params']['bonus_products']:
                        result_products.append({'id': bonus_product['id'],
                                                'count': promotion['params']['bonus_products_pcs']})
                if int(promotion['params']['conditions'][0]['id']) != 0:
                    for condition in promotion['params']['conditions']:
                        involved_products.append({'id': condition['id'],
                                                  'count': condition['pcs']})
                elif int(promotion['params']['conditions'][0]['id']) == 0 \
                        and int(promotion['params']['result_type']) == 3:
                    for involved_product in products:
                        involved_product_output = {'id': involved_product['product_id'],
                                                   'count': involved_product['count']}
                        if 'modification' in involved_product:
                            involved_product_output['modification'] = str(involved_product['modification']) \
                                .replace(' ', '').replace('\'', '\"')
                        if 'modificator_id' in involved_product:
                            involved_product_output['modification'] = str(involved_product['modificator_id']) \
                                .replace(' ', '').replace('\'', '\"')
                        involved_products.append(involved_product_output)
        promotion_products = []
        for product in products:
            promotion_products_output = {"id": product["product_id"], "count": product["count"]}
            if "modification" in product:
                promotion_products_output["modification"] = product["modification"]
            if "modificator_id" in product:
                promotion_products_output["modification"] = product["modificator_id"]
            promotion_products.append(promotion_products_output)
        promotion_output = {
            "id": str(promotion_id),
            "involved_products": involved_products,
            "result_products": result_products
        }
        data["promotion"] = [promotion_output]
    req_data = json.dumps(data)
    print(json.loads(req_data))
    logging.warning(str(json.loads(req_data)))
    headers = {
        'Content-Type': 'application/json',
        'Cookie': cfg.get('poster', 'cookie')
    }
    # Отправка онлайн-заказа
    response = requests.request("POST", url_createIncomingOrder, headers=headers, data=req_data)
    print('Ответ Poster POS:')
    print(response.json())
    logging.warning('Ответ Poster POS: ' + str(response.json()))


app.run()
