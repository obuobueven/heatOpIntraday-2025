from utils.emailTool.mymail import send

from utils.logTool.log_code import _logging


# _logging.error('测试错误日志')

# send('Text',['3346508677@qq.com'],'这是一封测试邮件',['test.py']) 


# continueVarKeys = ['a','b','c']

# dict = {
#     "a": [0.02, 0.03, 0.04],
#     "b": [0.01, 0.02, 0.03],
#     "c": [0.04, 0.06, 0.07],
#     "z": [1,1,1]
# }

# for key in continueVarKeys:
#     dict[key] = [0 if x < 0.05 else x for x in dict[key]]


# dict["z"] = [0 if p == 0 else z for p, z in zip(dict["c"], dict["z"])]


# print(dict)


# dict_control = {
#     'z_ghp_de': [1, 0, 1, 0],
#     'z_ghp_ht': [0, 1, 1, 0]
# }

# dict_control['z_ghp'] = [
#     de + ht for de, ht in zip(dict_control['z_ghp_de'], dict_control['z_ghp_ht'])
# ]
# print(dict_control)

# dict = {
#     "p_eb": [0, 1000, 2000, 4000]
# }

# dict['num_eb'] =[0 if p == 0 else 1 if p <= 3000/2 else 2 for p in dict['p_eb']]        # 电锅炉数量
# print(dict)

# import datetime

# timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# print(timestamp)

# # 将timestamp转换为毫秒级时间戳
# import time
# timestamp = time.time() * 1000
# print(int(timestamp))

# def get_hour_from_timestamp(timestamp):
#     # 将毫秒级时间戳转换为datetime对象
#     dt = datetime.datetime.fromtimestamp(timestamp / 1000)
#     print(dt)
#     # 获取小时数
#     hour = dt.hour
#     return hour

# print(get_hour_from_timestamp(timestamp))

# EPS = 1e-8
# heatingLoadMax = 2800
# exampleHeatLoad = min(v := [2000, 2800, 3500], key=lambda v: abs(heatingLoadMax - v) / (abs(heatingLoadMax) + EPS))
# print(exampleHeatLoad)
# exampleHeatLoad = 2000
# import pandas as pd

# example_data = pd.read_excel('basicStrategy/{}.xls'.format(exampleHeatLoad))
# currentProcedureID = example_data['procedureID'][12]
# print(int(currentProcedureID))


# import pytest


# def func(a, b):
#     return a + b
# @pytest.mark.parametrize("a, b, expected", [
#     (1, 2, 3),
#     (0, 0, 0),
#     (1, -2, -3),
# ])
# def test_addition(a, b, expected):
#     assert func(a, b) == expected

# @pytest.mark.skip(reason="跳过")
# def test_answer():
#     assert func(1, 2) == 3
    
# @pytest.mark.xfail(reason="预期失败")
# def test_failure():
#     assert func(1, 2) == 4


# alpha_points = list(range(2000, 3501, 100))  # 注意：3501 是为了包含 3500
# print(alpha_points)

# alpha_ratios = [round(point / 2724, 6) for point in alpha_points]
# print(alpha_ratios)


to_str = lambda x: ''.join(str(int(round(i, 0))) for i in x)

print(to_str([0.999999999999058]))
