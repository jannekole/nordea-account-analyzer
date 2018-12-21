#!/usr/bin/env python
# -*- coding: utf-8 -*-

import csv
import datetime
import yaml
import os

NORDEA_DATA_FOLDER = 'nordea_data'


def read_values(filename):
    with open(filename, 'r') as input_file:
        file_data = input_file.readlines()
        rows = [row.strip().split('\t') for row in file_data if row != '\r\n']
        return rows


def read_settings():
    with open('settings.yaml', 'r') as input_file:
        settings = yaml.load(input_file)
        return settings


class Account():
    def __init__(self, account_number, name, transactions=[], balance=0, balance_date=datetime.datetime.now().date()):
        self.account_number = account_number
        self.name = name
        self.transactions = []
        self.add_transactions(transactions)
        self.init_balance = balance
        self.init_balance_date = balance_date
        self.saaja_maksaja_includes = None
        self.viesti_includes = None
        # self.calculate_balances(balance, balance_date)


    def __str__(self):
        return '{} {} {}'.format(self.account_number, self.name, len(self.transactions))

    def add_transactions(self, transaction_list):
        transaction_list = [trans for trans in transaction_list if trans not in self.transactions]
        print('adding ', len(transaction_list))
        self.transactions = self.transactions + transaction_list
        print(len(self.transactions), 'transactions')
        dates = [trans.kirjauspaiva for trans in self.transactions]

    def calculate_balances(self):
        balance = self.init_balance
        balance_date = self.init_balance_date
        self.transactions = sorted(self.transactions, reverse=True, key=lambda transaction: transaction.kirjauspaiva)
        self.balances = []
        self.day_changes = []
        current_date = None
        current_date_change = 0
        for transaction in self.transactions:
            if current_date != transaction.kirjauspaiva:
                if current_date is not None:
                    self.day_changes.append({"date": current_date, "change": current_date_change})
                current_date = transaction.kirjauspaiva
                current_date_change = 0
            current_date_change = current_date_change + transaction.value
        self.day_changes.append({"date": current_date, "change": current_date_change})

        # self.balances.append({"amount": balance, "date": balance_date})
        date = balance_date
        for change in self.day_changes:
            change_date = change['date']
            while change_date != date:
                self.balances.append({"amount": balance, "date": date})
                try:
                    date = date - datetime.timedelta(days=1)
                except:
                    print(self.balances[-1])
                    raise
            balance = balance - change['change']
        self.balances.append({"amount": balance, "date": date})
        if self.name == 'Nordnet':
            print(self.balances)

    def add_transaction_if_included(self, transaction):
        if self.includes_transaction(transaction):
            opposite = transaction.opposite()
            if opposite not in self.transactions:
                self.transactions.append(opposite)

    def includes_transaction(self, transaction):
        if self.saaja_maksaja_includes is not None:
            if self.saaja_maksaja_includes.lower() in transaction.saaja_maksaja.lower():
                return True
        if self.viesti_includes is not None:
            if self.viesti_includes.lower() in transaction.viesti.lower():
                return True
        return False


class Transaction():
    def __init__(
        self, tili, row
        # kirjauspaiva, arvopaiva, maksupaiva, value, saaja_maksaja, tilinumero, bic,
        # tapahtuma, viite, maksan_viite, viesti, kortinnumero, kuitti
    ):
        while len(row) <= 12:
            row.append('')
        self.row = row
        self.tili = tili
        self.kirjauspaiva = self.parse_date(row[0])
        self.arvopaiva = self.parse_date(row[1])
        self.maksupaiva = self.parse_date(row[2])
        self.value = float(row[3].replace(',', '.'))
        self.saaja_maksaja = row[4].decode('utf-8')
        self.tilinumero = row[5]
        self.bic = row[6]
        self.tapahtuma = row[7]
        self.viite = row[8]
        self.maksan_viite = row[9]
        self.viesti = row[10]
        self.kortinnumero = row[11]
        self.kuitti = row[12]

    def __str__(self):
        return '{} {} {} {}'.format(self.tili, self.kirjauspaiva, self.value, self.saaja_maksaja)

    def parse_date(self, date_string):
        if not date_string:
            return ''
        date = datetime.datetime.strptime(date_string, '%d.%m.%Y').date()
        return date

    def __eq__(self, other):
        return self.__dict__ == other.__dict__

    def opposite(self):
        opposite = Transaction(self.tili, self.row)
        opposite.value = -self.value
        return opposite


class Assets():
    def __init__(self):
        self.accounts = {}
        self.settings = read_settings()
        self.virtual_accounts = []

    def transactions_from_folder(self):
        filenames = os.listdir(NORDEA_DATA_FOLDER)
        for filename in filenames:
            self.transactions_from_file(NORDEA_DATA_FOLDER + '/' + filename)

    def calculate_balances(self):
        for account in self.get_accounts():
            account.calculate_balances()

    def get_accounts(self):
        return [self.accounts[key] for key in self.accounts.keys()] + self.virtual_accounts

    def transactions_from_file(self, filename):
        print(filename)
        data = read_values(filename)
        tilinumero = data[0][1]

        transactions = [Transaction(tilinumero, row) for row in data[2:]]
        self.add_transactions(transactions, tilinumero)

    def add_transactions(self, transactions, tilinumero):
        if tilinumero in self.accounts:
            self.accounts[tilinumero].add_transactions(transactions)
        else:
            account_name = tilinumero
            account = Account(tilinumero, account_name, transactions, balance=self.settings.get('balances', {}).get(tilinumero, 0))
            self.add_account(account)
        for account in self.virtual_accounts:
            for transaction in transactions:
                account.add_transaction_if_included(transaction)

    def add_account(self, account):
        self.accounts[account.account_number] = account

    def external_accounts_from_settings(self):
        external_accounts = self.settings.get('externalaccounts', {})
        for name in external_accounts.keys():
            ext_account = Account(name, name, balance=self.settings.get('balances', {}).get(name))
            account_settings = external_accounts[name]
            ext_account.saaja_maksaja_includes = account_settings.get('saaja_maksaja')
            ext_account.viesti_includes = account_settings.get('viesti')
            self.virtual_accounts.append(ext_account)

    def classifications_from_settings(self):
        self.classifications = self.settings.get('classification')

    def get_all_transactions(self):
        transactions = []
        for account in self.get_accounts():
            transactions = transactions + account.transactions
        return transactions

    def classify_transactions(self, start, end):
        classified = {}
        for transaction in self.get_all_transactions():
            if start <= transaction.kirjauspaiva < end:
                self.add_to_classified(classified, transaction)
        return classified

    def add_to_classified(self, classified, transaction):
        saaja_maksaja = transaction.saaja_maksaja
        type = self.classify_saaja_maksaja(saaja_maksaja)
        self.add_to_dict(classified, type, transaction.value)

    def add_to_dict(self, sum_dict, key, value):
        if key in sum_dict:
            sum_dict[key] += value
        else:
            sum_dict[key] = value

    def classify_saaja_maksaja(self, saaja_maksaja):
        for key in self.classifications:
            try:
                for search_value in self.classifications[key]:
                    if search_value.lower() in saaja_maksaja.lower():
                        saaja_maksaja = key
            except:
                print(saaja_maksaja)
                print(type(saaja_maksaja))
                raise
        return saaja_maksaja



# tilinumero = data[0][1]
# transactions = [Transaction(tilinumero, row) for row in data[2:]]
# transactions2 = [Transaction(tilinumero, row) for row in data[2:]]

# account = Account(tilinumero, 'Käyttötili', transactions, balance=settings.get('balance', 0))


assets = Assets()


assets.external_accounts_from_settings()
assets.transactions_from_folder()
assets.classifications_from_settings()
assets.calculate_balances()
today = datetime.datetime.utcnow().date()

min_date = datetime.datetime(2016, 1, 1).date()
date = datetime.date.today()
months = [date]
spendings = []
total = {}
while date >= min_date:
    if date.day == 1:
        months.append(date)
    date -= datetime.timedelta(days=1)
for i in range(len(months) - 1):
    classified = assets.classify_transactions(months[i + 1], months[i])
    spendings.append(classified)
    for key in classified:
        assets.add_to_dict(total, key, classified[key])
    print(months[i + 1].strftime("%B %Y"))
    print(sorted([[key, classified[key]] for key in classified], key=lambda a: a[1]))
sorted_pairs = sorted([[key, total[key]] for key in total], key=lambda a: a[1])
ordered_targets = [p[0] for p in sorted_pairs]
spending_matrix = []
spending_matrix.append([None] + [t.encode('utf-8') for t in ordered_targets])

for i, spending in enumerate(spendings):
    spending_matrix.append([months[i + 1]] + [spending.get(key, 0) for key in ordered_targets])

print(total)
print(sorted_pairs)

# print(external_names)
# for name in external_names:
#     print(external_accounts[name])
csv_headers = ['date', 'balance']

account_names = [acc.name for acc in assets.get_accounts()]

csv_matrix = []
i = 0
values = {}
while True:
    row = []
    no_data_count = 0
    date = None
    for account in assets.get_accounts():
        try:
            balance = account.balances[i]
            values[account.name] = balance['amount']
            date = balance['date']
        except IndexError:
            no_data_count += 1

        row.append(values.get(account.name, 0))
        value = balance
    i += 1
    value_list = [values[key] for key in values.keys()]
    total = sum(value_list)
    csv_matrix.append([date] + row + [total])
    if no_data_count == len(account_names):
        break
    if i > 10000:
        print('too much')
        break

csv_matrix = list(reversed(csv_matrix))
csv_matrix = [['date'] + account_names + ['total']] + csv_matrix

filtered_csv = []
for index, row in enumerate(csv_matrix):
    if index % 5 == 0:
        filtered_csv.append(row)


with open('out_data.csv', 'w') as out_csv:
    writer = csv.writer(out_csv)
    writer.writerows(csv_matrix)

with open('spending.csv', 'w') as out_csv:
    writer = csv.writer(out_csv)
    writer.writerows(spending_matrix)
