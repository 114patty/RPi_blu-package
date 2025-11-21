import pymongo
from PyQt5 import  QtCore
from PyQt5.QtCore import QObject
 


import yaml



class DataBase(QtCore.QThread):
    def __init__(self,database_name,collection_name) -> None:
        super().__init__()
        self.client = None #creat a connect Object
        self.db = None #create or select a database
        self.collection = None #create or select a collection 
        self.data = None # for insert data 
        self.query = None # for search data 

        self.database_name = database_name
        self.collection_name  =collection_name


        
        try:
            with open('config.yaml', 'r') as config_file:
                config_data = yaml.safe_load(config_file)
                address = config_data["database"]["address"]

            # 连接到MongoDB
            self.client = pymongo.MongoClient(address)  # 替换为您的MongoDB连接字符串uuid

            # 创建或选择数据库
            self.db = self.client[self.database_name]

            # 创建或选择集合
            self.collection = self.db[self.collection_name]

        except Exception as e:
            print(e)

        
    def insert_data(self,data):
        # 插入文档
        self.data = data
        inserted_doc = self.collection.insert_one(self.data)
        print(f"Inserted document ID: {inserted_doc.inserted_id}")
