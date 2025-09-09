import json
import datetime
import pyscipopt as opt
import numpy as np
import xlwt 
import pandas as pd
from enum import Enum


from utils.emailTool.mymail import send
from utils.logTool.log_code import _logging


import pytest   # ! 测试使用
TEST_ALF = 1    # ! 测试使用

# 返回码枚举类
class RespCode(Enum):
    ErrorState = 100        # 其他错误
    InfeasibleState = 101   # 模型不可行/无解
    EquipErrorState = 102   # 设备故障

    SuccessState = 200      # 最优解
    TimelimitState = 201    # 求解器超时，返回可行解
    ProcedureLack = 202     # 流程缺失，匹配示例流程输出


# 输出字段与模型变量的映射
OUTPUT_FIELDS_MAPPING = {
    "procedureID": "procedureID",
    "powerBuyIntraday": "p_pur",
    "powerBuyStateIntraday": "z_pur",
    "hydrogenBuyIntraday": "h_pur",
    "pvIntraday": "p_pv",
    "fcPowerIntraday": "p_fc",
    "fcHeatIntraday": "g_fc",
    "mFcIntraday": "m_h_fc",
    "fcStateIntraday": "z_fc",
    "fc2deStateIntraday": "z_fc_de",
    "fc2htStateIntraday": "z_fc_ht",
    "ebPowerIntraday": "p_eb",
    "ebHeatIntraday": "g_eb",
    "ebStateIntraday": "z_eb",
    "eb2deStateIntraday": "z_eb_de",
    "eb2htStateIntraday": "z_eb_ht",
    "ebNumIntraday": "num_eb",
    "eb1UnitPowerIntraday": "p_eb1",
    "eb2UnitPowerIntraday": "p_eb2",
    "ghpHeatIntraday": "g_ghp",
    "ghpStateIntraday": "z_ghp",
    "ghp2deStateIntraday": "z_ghp_de",
    "ghp2htStateIntraday": "z_ghp_ht",
    "htStateIntraday": "z_ht",
    "ht2deStateIntraday": "z_ht_sto",
    "ahpPowerIntraday": "p_ahp",
}
# ! 测试用函数
def to_csv(res, filename):
    """生成excel输出文件

    Args:
        res (_type_): 结果json，可以包括list和具体值
        filename (_type_): 文件名，不用加后缀
    """
    items = list(res.keys())
    wb = xlwt.Workbook()
    total = wb.add_sheet('test')
    for i in range(len(items)):
        total.write(0,i,items[i])
        if type(res[items[i]]) == list:
            # print(items[i])
            for j in range(len(res[items[i]])):
                total.write(j+1,i,(res[items[i]])[j])
        else:
            # print(items[i])
            total.write(1,i,(res[items[i]]))
    wb.save(filename+".xls")
# HACK: 没有加入空气源热泵
# 流程中缺少燃料电池蓄热


def build_output(
    respCode, objectiveValue=None, dict_control:dict=None, currentTimeStamp=None
):
    """
    Args:
        respCode (_type_): 响应码
        objectiveValue: 目标值. Defaults to None.
        dict_control: 设备控制字典. Defaults to None.
        currentTimeStamp: 当前时间戳. Defaults to None.
        currentProcedureID: 当前流程ID. Defaults to None.

    Returns:
        _type_: 输出字典 => result
    """
    result = {
        "respCode": respCode,
        "objectiveValue": objectiveValue if (respCode == RespCode.SuccessState.value or respCode == RespCode.TimelimitState.value) else 0.0,
        "output": []
    }
    for key in list(OUTPUT_FIELDS_MAPPING.keys()):
        item = {
            "key": key,
            "type": "timeseries",
            "time": [currentTimeStamp],
            "value": [0]  # 默认值为 0
        }
        if (respCode == RespCode.SuccessState.value or 
            respCode == RespCode.ProcedureLack.value or 
            respCode == RespCode.TimelimitState.value) and dict_control is not None:
            try:
                item["value"] = [dict_control[OUTPUT_FIELDS_MAPPING[key]][0]]
                result["output"].append(item)
            except BaseException as E:
                handle_error("写入调度结果出错", E)
                raise Exception
        else:
            result["output"].append(item)
    return result


def handle_error(error_msg_prefix,E):
    '''
        处理异常错误,发送邮件通知
    '''
    _logging.error("error_msg_prefix: {}".format(E)) # 记录错误日志
    print("error_msg_prefix: {}".format(E)) 

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    emailText = f"{timestamp}: {error_msg_prefix}: {E}"  # 邮件正文
    file_list = []
    send('Text',receivers = ['3346508677@qq.com'],text = emailText,file_list = file_list)# 发送信息+文件(模型信息.lp dict_opt_control.xls)
    return True


'''设备状态编码说明：
燃料电池: op1-op2-op3
    op1: 启停(1=运行,0=停机)
    op2: 供能控制(1=供末端,0=不供末端)
    op3: 蓄热控制(1=蓄热,0=不蓄热)
    示例："110" → 运行,供末端，不蓄热
-------------------------------------
电锅炉: op1-op2-op3-op4
    op1: 启停
    op2: 供能控制
    op3: 蓄热控制
    op4: 运行台数
    示例："1102" → 2台运行,供末端
-------------------------------------
地源热泵: op1-op2-op3
    op1: 启停
    op2: 供能控制
    op3: 蓄热控制
    示例："101" → 运行,蓄热
-------------------------------------
储热罐: op1-op2
    op1: 启停
    op2: 储放

# 格式： "燃料电池 - 电锅炉 - 地源热泵 - 储热罐"
'''
Operation_mapping = {
    "110-1102-101-10": "10001", # 燃料电池+2台电锅炉供应末端负荷；地源热泵蓄热
    "110-1102-000-11": "10002", # 燃料电池+2台电锅炉+储热罐供应末端负荷；地源热泵停机
    "110-1101-101-10": "10003", # 燃料电池+1台电锅炉供应末端负荷；地源热泵蓄热
    "110-1101-000-11": "10004", # 燃料电池+1台电锅炉+储热罐供应末端负荷；地源热泵停机 
    "110-1011-110-10": "10005", # 燃料电池+地源热泵供应末端负荷；1台电锅炉蓄热
    "110-0000-101-10": "10006", # 燃料电池供应末端负荷；地源热泵蓄热
    "000-0000-000-11": "10007", # 储热罐供应末端符合；地源热泵停机
    # 以上为原有
    "000-0000-110-00": "10008",
    "000-1101-000-00": "10009",
    "000-1012-110-10": "10010",
    "000-1101-000-11": "10011",
    "000-0000-110-11": "10012",
    "110-0000-110-00": "10013",
    "110-0000-000-11": "10014",
    "110-1101-000-00": "10015",
    "110-1012-000-10": "10016",
    "110-1011-000-10": "10017",
    "000-1101-110-00": "10018",
    "000-1101-101-10": "10019",
    "000-1102-101-10": "10020",
    "110-1101-110-00": "10021",
    "110-1102-000-00": "10022",
    "000-1102-000-00": "10023",
    "110-1102-000-11": "10024",
    # 以上为第一次更新
    "000-1102-000-11": "10025",
    "000-1102-110-00": "10026", 
    # 以上为第二次更新
    "000-1101-110-11": "10027",
    "110-1012-110-10": "10028",
    "000-1102-110-11": "10029",
    # 以上为负荷全覆盖更新
}

def get_Procedure_ID(fc, eb, ghp, ht):
    """
    arguments:
        fc (list): 燃料电池状态，如 [1, 1, 0]
        eb (list): 电锅炉状态，如 [1, 1, 0, 2] 或 [1,1,1,0]
        ghp (list): 地源热泵状态，如 [1, 0, 1]
        ht (list): 储热罐状态，如 [1,1]
    return:
        str or None: 匹配的流程 ID，未匹配返回 None
    """
    # 将每个设备的状态列表转换为字符串
    to_str = lambda x: ''.join(str(int(round(i, 0))) for i in x)

    key = f"{to_str(fc)}-{to_str(eb)}-{to_str(ghp)}-{to_str(ht)}"
    if Operation_mapping.get(key, 'None') == 'None':
        _logging.info("未匹配到流程,流程码为:{}".format(key))
    return Operation_mapping.get(key, 'None')  # 匹配则返回流程id，不匹配则返回none
def get_hour_from_timestamp(timestamp):
    # 将毫秒级时间戳转换为datetime对象
    dt = datetime.datetime.fromtimestamp(timestamp / 1000)
    # 获取小时数
    hour = dt.hour
    return hour

def data_process(data):
    # 提取时间数据
    times_pre = data['input'][0]['time']
    times_cur = data['input'][3]['time']
    hour_cur = get_hour_from_timestamp(times_cur[0])
    times_new = times_pre[:24 - hour_cur]
    new_data = {
        "time": [x + 30*60000 for x in times_new],  # 时间后移三十分钟
        "hour_cur": hour_cur,
        "ghpCoolRt": [0],  # 供热季
        "htState": [0],  # 设置储能罐故障状态，0：不出故障
        "hydrogenStorageState": [0]
    }

    # 将所有键值对添加到数据字典中
    for item in data["input"]:
        new_data[item["key"]] = item["value"]  # 保持为原列表

    return new_data

def output_CleanAndProcess(dict):
    '''
        description: 对输出结果进行清洗和处理
        - 将极小值置为0
        - 处理松弛的01量
        - 得到设备状态
    '''
    continueVarKeys = [
        "p_pv",
        "m_h_fc",
        "p_fc",
        "g_fc",
        "p_ghp",
        "g_ghp",
        'g_ghp_de',
        'g_ghp_ht',
        "p_eb",
        "g_eb",
        'g_eb_de',
        'g_eb_ht',
        'p_ahp',
        'g_ahp',
        'g_ht',
        "p_bs_ch",
        'p_bs_dis',
        "p_pur",
        "h_pur",
    ]

    for key in continueVarKeys:
        dict[key] = [0 if x < 0.01 else x for x in dict[key]]

    dict['z_pur'] = [0 if p == 0 else z for p, z in zip(dict["p_pur"], dict["z_pur"])]      # 处理购电01量
    dict['z_ghp'] = [z_de + z_ht for z_de, z_ht in zip(dict['z_ghp_de'], dict['z_ghp_ht'])] # 地源热泵开关机

    dict['z_fc'] = [0 if p == 0 else 1 for p in dict["p_fc"]]                              # 处理燃料电池01量
    dict['z_fc_de'] = [1 * z_fc for z_fc in dict['z_fc']]                                     # 燃料电池只供管道
    dict['z_fc_ht'] = [0] * len(dict['z_fc'])                                                 # 燃料电池只供管道

    dict['z_eb'] = [0 if p == 0 else 1 for p in dict["p_eb"]]                              # 处理电锅炉01量
    dict['z_eb_de'] = [0 if g == 0 else 1 for g in dict['g_eb_de']]                           # 电锅炉供管道
    dict['z_eb_ht'] = [0 if g == 0 else 1 for g in dict['g_eb_ht']]                           # 电锅炉蓄热
    dict['num_eb'] = [0 if p == 0 else 1 if p <= 3000/2 else 2 for p in dict['p_eb']]        # 电锅炉数量
    dict['p_eb1'] = [1500.0 if p > 3000/2 else p for p in dict['p_eb']]                     # 电锅炉1功率
    dict['p_eb2'] = [0 if p < 3000/2 else p-1500 for p in dict['p_eb']]                     # 电锅炉2功率

    dict['z_ht'] = [
        1 if g_ht > 0 or (g_eb_ht + g_ghp_ht) > 0 else 0
        for g_ht, g_eb_ht, g_ghp_ht in zip(
            dict["g_ht"], dict["g_eb_ht"], dict["g_ghp_ht"]
        )
    ]   # 储热罐启用标志
    dict['z_ht_sto'] = [(1 - z) * z_ht for z, z_ht in zip(dict["z_ht_sto"], dict["z_ht"])] # 储热罐工况描述
    
    dict['procedureID'] = [
        get_Procedure_ID(
            fc = [dict['z_fc'][i], dict['z_fc_de'][i], dict['z_fc_ht'][i]],
            eb = [dict['z_eb'][i], dict['z_eb_de'][i], dict['z_eb_ht'][i], dict['num_eb'][i]],
            ghp = [dict['z_ghp'][i], dict['z_ghp_de'][i], dict['z_ghp_ht'][i]],
            ht = [dict['z_ht'][i], dict['z_ht_sto'][i]],
            )
        for i in range(len(dict['z_fc']))
    ]

    
    return dict

def get_data(data, key):
    """
        从data中读取并校验数据
    """
    # 检查键是否存在
    if key not in data:
        raise KeyError(f"Missing required key: {key}")
    
    value = data[key]
    
    # 检查空列表
    if len(value) == 0:
        raise ValueError(f"{key} is an empty list")
    
    # 检查第一个元素是否为 None
    if len(value) > 0 and value[0] is None:
        raise ValueError(f"{key}[0] is None")
    
    return value

def get_Procedure_id(fc, eb, ghp, ht):
    """
    arguments:
        fc (list): 燃料电池状态，如 [1, 1, 0]
        eb (list): 电锅炉状态，如 [1, 1, 0, 2] 或 [1,1,1,0]
        ghp (list): 地源热泵状态，如 [1, 0, 1]
        ht (list): 储热罐状态，如 [1,1]
    return:
        str or None: 匹配的流程 ID，未匹配返回 None
    """
    # 将每个设备的状态列表转换为字符串
    to_str = lambda x: ''.join(str(int(round(i, 0))) for i in x)

    key = f"{to_str(fc)}-{to_str(eb)}-{to_str(ghp)}-{to_str(ht)}"
    if Operation_mapping.get(key, "None") == "None":
        _logging.info("未匹配到流程,流程码为:{}".format(key))

    return Operation_mapping.get(key, "None")  # 匹配则返回流程id，不匹配则返回none

def handlingEquipmentErrorFunc(equipmentErrorList:list):
    '''
        设备故障处理函数
        arguments:
            equipmentErrorList (list): 发生故障的设备列表
        return:
            None
    '''
    
    print("this is handlingEquipmentErrorFunc")
    return RespCode.EquipErrorState.value
def Optimization(data, config):
    """
    Args:
        data (dict): input data including energy load, device power and fault state
        config (dict): config, including energy price 
    Returns:
        dict: intra_day optimal operation results
    """

    '''
        data处理: 时间戳提取;数据形式转换
    '''
    timeStamps = next(
        (
            item["time"]
            for item in data
            if isinstance(item.get("time"), list) and len(item["time"]) > 1
        ),
        None,  # 默认值
    )
    print("时间序列戳:", timeStamps)
    currentTimeStamp = timeStamps[0]
    currentHour = get_hour_from_timestamp(currentTimeStamp) # 获取当前小时,用于流程缺失匹配 时间输出
    data = {item["key"]: item["value"] for item in data}    # 数据转为字典形式

    
    c_water = 4.2e3 / 3600  # 水的比热容 (kWh/(t·K))  
    M = 3000  # 优化模型线性化所需大数
    period = 24 # 优化窗口
    
    # * 读取设备故障状态
    equipmentErrorList = [key for key, value in data.items() if 'StateRT' in key and value == [1]]
    if equipmentErrorList != []:
        for key in equipmentErrorList:
            _logging.error(f"设备{key.replace('StateRT', '')}发生故障")
            print(f"设备{key.replace('StateRT', '')}发生故障")
        respCode = handlingEquipmentErrorFunc(equipmentErrorList)
        return
    else:
        pass
    
    # * 读取储能设备状态

    htTemperatureRT = get_data(data, "htTemperatureStart")[0]
    bsSocRT = get_data(data, "bessSocStart")[0]

    # 读取内部配置文件
    try:
        with open("./device_setting.json", "rb") as f:
            parameter_json = json.load(f)
            print("读取参数配置文件<device_setting.json>成功")
    except BaseException as E:
        handle_error("读取参数配置文件<device_setting.json>出错", E)
        raise Exception

    # 初始化设备参数
    try:
        # GHP, 浅层地源热泵
        eta_ghp = parameter_json['device']['ghp']['eta_ghp']
        eta_pump_ghp = parameter_json['device']['ghp']['eta_pump']
        # EB, 电锅炉
        eta_eb = parameter_json['device']['eb']['eta_eb']
        eta_pump_eb = parameter_json['device']['eb']['eta_pump']
        # AHP, 空气源热泵
        eta_ahp = parameter_json['device']['ahp']['eta_ahp']
        # 拟合得到的ahp cop计算式：cop=k_t_env*t_env + k_t_out*t_out
        # k_t_env = parameter_json['device']['ahp']['k_t_env']
        # k_t_ahp = parameter_json['device']['ahp']['k_t_ahp']
        # eta_ahp_base = parameter_json['device']['ahp']['eta_ahp_base']
        eta_pump_ahp = parameter_json['device']['ahp']['eta_pump']
        # FC, 燃料电池
        eta_fc_p = parameter_json['device']['fc']['eta_p']
        eta_fc_g = parameter_json['device']['fc']['eta_g']
        eta_pump_fc = parameter_json['device']['fc']['eta_pump']
        theta_fc_ex = parameter_json['device']['fc']['theta_ex']
        # g_p_ratio_200 = parameter_json['device']['fc']['power_200']['g_p_ratio']
        # g_p_ratio_400 = parameter_json['device']['fc']['power_400']['g_p_ratio']
        # g_p_ratio_600 = parameter_json['device']['fc']['power_600']['g_p_ratio']
        # k_g_p_200 = parameter_json['device']['fc']['power_200']['k_g_p']
        # b_g_p_200 = parameter_json['device']['fc']['power_200']['b_g_p']
        # k_g_p_400 = parameter_json['device']['fc']['power_400']['k_g_p']
        # b_g_p_400 = parameter_json['device']['fc']['power_400']['b_g_p']
        # k_g_p_600 = parameter_json['device']['fc']['power_600']['k_g_p']
        # b_g_p_600 = parameter_json['device']['fc']['power_600']['b_g_p']
        # HT, 储热罐
        eta_ht_loss = parameter_json['device']['ht']['eta_loss']
        # eta_pump_ht = parameter_json['device']['ht']['eta_pump']
        # BS, 蓄电池
        # eta_bs_loss = parameter_json['device']['bs']['eta_loss']
        # PV, 光伏
        eta_pv = parameter_json['device']['pv']['eta_pv']
        # PIPE, 管网
        eta_pipe_loss = parameter_json['device']['pipe']['eta_loss']
        eta_pump_pipe = parameter_json['device']['pipe']['eta_pump']
        # GTW, 地热井
        m_gtw = parameter_json['device']['gtw']['water_max']
        t_gtw_in_min = parameter_json['device']['gtw']['t_in_min']  # 地热井进水温度
    except BaseException as E:
        handle_error("读取<device_setting.json>中设备参数出错", E)
        raise Exception

    try:
        # 读取容量
        p_ghp_max = parameter_json['device']['ghp']['power_max']  # 浅层地源热泵额定功率
        p_eb_max = parameter_json['device']['eb']['power_max']  # 电锅炉额定功率
        p_ahp_max = parameter_json['device']['ahp']['power_max']  # 空气源热泵额定功率
        p_fc_max = parameter_json['device']['fc']['power_max']  # 燃料电池额定功率
        m_ht_sto = parameter_json['device']['ht']['water_max']  # 储热罐水量
        p_bs_sto_ub = parameter_json['device']['bs']['power_max']  # 蓄电池储能上限
        p_bs_sto_lb = parameter_json['device']['bs']['power_min']  # 蓄电池储能下限
        p_pv_max = parameter_json['device']['pv']['power_max']  # 光伏发电装机容量
    except BaseException as E:
        handle_error("读取<device_setting.json>中设备容量出错", E)
        raise Exception

    try:
        # 读取初始化边界
        t_ht_sto_ub = parameter_json['device']['ht']['t_max']
        t_ht_sto_lb = parameter_json['device']['ht']['t_min']
        t_de_ub = parameter_json['device']['pipe']['t_max']  # 管网供回水温度上限
        t_de_lb = parameter_json['device']['pipe']['t_min']  # 管网供回水温度下限
        t_ghp_ub = parameter_json['device']['ghp']['t_max']  # 浅层地源热泵出水温度上限
        t_ghp_lb = parameter_json['device']['ghp']['t_min']  # 浅层地源热泵出水温度下限
        t_eb_ub = parameter_json['device']['eb']['t_max']  # 电锅炉出水温度上限
        t_eb_lb = parameter_json['device']['eb']['t_min']  # 电锅炉出水温度下限
        t_ahp_ub = parameter_json['device']['ahp']['t_max']  # 空气源热泵出水温度上限
        t_ahp_lb = parameter_json['device']['ahp']['t_min']  # 空气源热泵出水温度下限
        t_fc_ub = parameter_json['device']['fc']['t_max']  # 燃料电池出水温度上限
        t_fc_lb = parameter_json['device']['fc']['t_min']  # 燃料电池出水温度下限

        m_ghp_ub = parameter_json['device']['ghp']['water_max']  # 浅层地源热泵循环水量上限
        m_ghp_lb = parameter_json['device']['ghp']['water_min']  # 浅层地源热泵循环水量下限
        m_eb_ub = parameter_json['device']['eb']['water_max']
        m_eb_lb = parameter_json['device']['eb']['water_min']
        m_ahp_ub = parameter_json['device']['ahp']['water_max']
        m_ahp_lb = parameter_json['device']['ahp']['water_min']
        m_fc_ub = parameter_json['device']['fc']['water_max']
        m_fc_lb = parameter_json['device']['fc']['water_min']
        m_ht_ub = parameter_json['device']['ht']['water_max']
        m_ht_lb = parameter_json['device']['ht']['water_min']
        m_de_ub = parameter_json['device']['pipe']['water_max']  # 管网循环水量上限
        m_de_lb = parameter_json['device']['pipe']['water_min']  # 管网循环水量下限
    except BaseException as E:
        handle_error("读取<device_setting.json>中设备边界出错", E)
        raise Exception

    try:
        # 读取能源价格/储能设备状态<arg:config>
        lambda_ele_in = config['ele_TOU_price']
        hydrogen_price = config['hydrogen_price']
        p_demand_price = config['demand_electricity_price']
    except BaseException as E:
        handle_error("读取<config.json>中能源价格出错", E)
        raise Exception

    # 读取data中的负荷信息
    try:
        p_load = get_data(data, 'powerLoadPrediction24h')  # 电负荷预测
        print("TEST_ALF:", TEST_ALF)    # ! 测试使用
        g_load = [g * TEST_ALF for g in get_data(data, 'heatingLoadPrediction24h')]  # ! 测试使用
        # * g_load = get_data(data, 'heatingLoadPrediction24h') # 热负荷预测
        t_env  = get_data(data, 'envTemperaturePrediction24h')  # 环境温度预测
        pv_gen = get_data(data, 'pvPrediction24h')  # 光伏发电预测
    except BaseException as E:
        handle_error("读取<config.json>中负荷信息出错", E)
        raise Exception

    # 初始化模型
    model = opt.Model()
    # 添加变量
    opex = model.addVar(vtype='C', lb=0, name="opex")  # 总运行成本
    opex_t = [model.addVar(vtype='C', lb=0, name=f"opex[{t}]") for t in range(period)]  # 每个时段的运行成本

    z_pur = [model.addVar(vtype='B', name=f"z_pur[{t}]") for t in range(period)]

    z_ghp_ht = [model.addVar(vtype='B', name=f"z_ghp_ht[{t}]") for t in range(period)]
    z_ghp_de = [model.addVar(vtype='B', name=f"z_ghp_de[{t}]") for t in range(period)]

    z_eb = [model.addVar(vtype='B', name=f"z_eb[{t}]") for t in range(period)]# 电锅炉工况描述
    # z_fc = [model.addVar(vtype='B', name=f"z_fc[{t}]") for t in range(period)]  # 燃料电池工况描述
    z_ht_sto = [model.addVar(vtype='B', name=f"z_ht_sto[{t}]") for t in range(period)]  # 储热罐工况描述

    # 电网
    p_pur = [model.addVar(vtype='C', lb=0, name=f"p_pur[{t}]") for t in range(period)]  # 从电网购电量
    # 氢源
    h_pur = [model.addVar(vtype='C', lb=0, name=f"h_pur[{t}]") for t in range(period)]
    # 末端
    t_de = [model.addVar(vtype='C', lb=t_de_lb, ub=t_de_ub, name=f"t_de[{t}]") for t in range(period)]
    # 地源热泵
    g_ghp = [model.addVar(vtype='C', lb=0, name=f"g_ghp[{t}]") for t in range(period)]
    g_ghp_ht = [model.addVar(vtype='C', lb=0, name=f"g_ghp_ht[{t}]") for t in range(period)]
    g_ghp_de = [model.addVar(vtype='C', lb=0, name=f"g_ghp_de[{t}]") for t in range(period)]
    t_ghp = [model.addVar(vtype='C', lb=0, name=f"t_ghp[{t}]") for t in range(period)]
    p_pump_ghp = [model.addVar(vtype='C', lb=0, name=f"p_pump_ghp[{t}]") for t in range(period)]
    # 电锅炉
    p_eb = [model.addVar(vtype='C', lb=0, ub=p_eb_max, name=f"p_eb[{t}]") for t in range(period)]
    g_eb = [model.addVar(vtype='C', lb=0, name=f"g_eb[{t}]") for t in range(period)]
    g_eb_ht = [model.addVar(vtype='C', lb=0, name=f"g_eb_ht[{t}]") for t in range(period)]
    g_eb_de = [model.addVar(vtype='C', lb=0, name=f"g_eb_de[{t}]") for t in range(period)]
    t_eb = [model.addVar(vtype='C', lb=t_eb_lb, ub=t_eb_ub, name=f"t_eb[{t}]") for t in range(period)]
    p_pump_eb = [model.addVar(vtype='C', lb=0, name=f"p_pump_eb[{t}]") for t in range(period)]
    # 空气源热泵
    p_ahp = [model.addVar(vtype='C', lb=0, ub=p_ahp_max,
                              name=f"p_ahp[{t}]") for t in range(period)]
    g_ahp = [model.addVar(vtype='C', lb=0, name=f"g_ahp[{t}]") for t in range(period)]
    t_ahp = [model.addVar(vtype='C', lb=t_ahp_lb,ub=t_ahp_ub, name=f"t_ahp[{t}]") for t in range(period)]
    p_pump_ahp = [model.addVar(vtype='C', lb=0, name=f"p_pump_ahp[{t}]") for t in range(period)]  
    # 燃料电池
    m_h_fc = [model.addVar(vtype='C', lb=0, name=f"m_h_fc[{t}]") for t in range(period)]
    p_fc = [model.addVar(vtype='C', lb=0, ub=p_fc_max,name=f"p_fc[{t}]") for t in range(period)]
    g_fc = [model.addVar(vtype='C', lb=0, name=f"g_fc[{t}]") for t in range(period)]
    g_fc_ht = [model.addVar(vtype='C', lb=0, name=f"g_fc_ht[{t}]") for t in range(period)]
    g_fc_de = [model.addVar(vtype='C', lb=0, name=f"g_fc_de[{t}]") for t in range(period)]
    t_fc = [model.addVar(vtype='C', lb=t_fc_lb, ub=t_fc_ub, name=f"t_fc[{t}]") for t in range(period)]
    p_pump_fc = [model.addVar(vtype='C', lb=0, name=f"p_pump_fc[{t}]") for t in range(period)]
    # 储热罐
    g_ht = [model.addVar(vtype='C', lb=0, name=f"g_ht[{t}]") for t in range(period)]
    t_ht_sto = [model.addVar(vtype='C', lb=t_ht_sto_lb, ub=t_ht_sto_ub,
                                name=f"t_ht_sto[{t}]") for t in range(period)]
    t_ht = [model.addVar(vtype='C', lb=0, ub=t_ht_sto_ub, name=f"t_ht[{t}]") for t in range(period)]
    # 蓄电池
    p_bs_sto = [model.addVar(vtype='C', lb=p_bs_sto_lb, ub=p_bs_sto_ub,
                                name=f"p_bs_sto[{t}]") for t in range(period)]
    p_bs_ch = [model.addVar(vtype='C', lb=0, ub=p_bs_sto_ub-p_bs_sto_lb,
                                name=f"p_bs_ch[{t}]") for t in range(period)]
    p_bs_dis = [model.addVar(vtype='C', lb=0, ub=p_bs_sto_ub-p_bs_sto_lb,
                                name=f"p_bs_dis[{t}]") for t in range(period)]
    # PIPE,管道
    t_supply = [model.addVar(vtype='C', lb=0, name=f"t_supply[{t}]") for t in range(period)]  
    m_de = [model.addVar(vtype='C', lb=m_de_lb, ub=m_de_ub,
                              name=f"m_de[{t}]") for t in range(period)]
    M_de = 100000  # 管网内水量
    T_de = [model.addVar(vtype='C', lb=t_de_lb, name=f"T_de[{t}]") for t in range(period)]  # 管网内平均水温
    p_pump_pipe = [model.addVar(vtype='C', lb=0, name=f"p_pump_pipe[{t}]") for t in range(period)]  # 管网循环泵功率

    # PV
    p_pv = [model.addVar(vtype='C', lb=0, name=f"p_pv[{t}]") for t in range(period)]  # 光伏发电功率

    '''
        添加约束：能力平衡，设备约束
    '''
    # 能量平衡
    for t in range(period):
        # 电力平衡约束
        model.addCons(
            p_pur[t] + p_pv[t] + p_fc[t] + p_bs_dis[t]
            == p_load[t] + (z_ghp_de[t]+z_ghp_ht[t]) * p_ghp_max + p_eb[t] + p_ahp[t] + p_bs_ch[t]
            + p_pump_ghp[t] + p_pump_eb[t] + p_pump_ahp[t] + p_pump_fc[t] + p_pump_pipe[t]
        )
        model.addCons(
            g_ghp_de[t] + g_eb_de[t] + g_ahp[t] + g_fc[t] + g_ht[t] == g_load[t]
        )
        model.addCons(h_pur[t] == m_h_fc[t])
        model.addCons(
           m_ghp_lb * t_ghp[t] + m_eb_lb * t_eb[t] + m_ahp_lb * t_ahp[t] + m_fc_lb * t_fc[t] + m_ht_lb * t_ht[t]
            == m_de_lb * t_supply[t]
        )

        model.addCons(p_pur[t] <= z_pur[t] * M)
        ''' 地源热泵紧放热约束'''
        model.addCons(g_ghp_ht[t] <= z_ghp_ht[t] * M)
        model.addCons(g_ghp_de[t] <= z_ghp_de[t] * M)
        model.addCons(g_ghp[t] == z_ghp_ht[t] * g_ghp_ht[t] + z_ghp_de[t] * g_ghp_de[t])
        model.addCons(z_ghp_de[t] + z_ghp_ht[t] <= 1)  # 浅层地源热泵工况约束
        model.addCons(g_eb[t] == z_eb[t]* g_eb_ht[t] + (1 - z_eb[t]) * g_eb_de[t])
        '''电锅炉紧放热约束'''
        model.addCons(g_eb_ht[t] <= z_eb[t] * M)
        model.addCons(g_eb_de[t] <= (1 - z_eb[t]) * M)
        #// model.addCons(z_eb_de[t] + z_eb_ht[t] <= 1)

        # model.addCons(g_fc[t] == z_fc[t] * g_fc_ht[t] + (1 - z_fc[t]) * g_fc_de[t])
        #// model.addCons(z_fc_de[t] + z_fc_ht[t] <= 1)

        # model.addCons(g_ghp_ht[t] + g_eb_ht[t] + g_fc_ht[t] <= z_ht_sto[t] * M)
        model.addCons(g_ghp_ht[t] + g_eb_ht[t] <= z_ht_sto[t] * M)

        model.addCons(g_ht[t] <= (1 - z_ht_sto[t]) * M)

        #// model.addCons(g_ghp[t] == eta_ghp[t] * z_ghp[t] * p_ghp_max)
        model.addCons(g_ghp[t] == eta_ghp * (z_ghp_de[t] + z_ghp_ht[t]) * p_ghp_max)
        model.addCons(g_ghp[t] * z_ghp_de[t] == c_water * m_ghp_lb * (t_ghp[t] - t_de[t]))
        model.addCons(p_pump_ghp[t] == eta_pump_ghp * m_ghp_lb)
        #// model.addCons(g_gtw[t] == g_ghp[t] - z_ghp[t] * p_ghp_max)

    model.addCons(opt.quicksum(z_ghp_ht[t]+z_ghp_de[t] for t in range(period)) 
                            <= parameter_json['device']['ghp']['max_time'])  # 浅层地源热泵最大工作时长

    # 设备约束
    for t in range(period):
        # EB
        model.addCons(g_eb[t] == eta_eb * p_eb[t])
        model.addCons(g_eb[t]*(1-z_eb[t])==c_water*m_eb_lb*(t_eb[t]-t_de[t]))
        model.addCons(p_pump_eb[t] == eta_pump_eb * m_eb_lb)

        # AHP
        model.addCons(g_ahp[t] == eta_ahp * p_ahp[t])
        model.addCons(g_ahp[t] == c_water * m_ahp_lb * (t_ahp[t] - t_de[t]))
        model.addCons(p_pump_ahp[t] == eta_pump_ahp * m_ahp_lb)

        # FC
        model.addCons(p_fc[t] == eta_fc_p * m_h_fc[t])
        model.addCons(g_fc[t] == eta_fc_g/eta_fc_p*theta_fc_ex * p_fc[t])
        model.addCons(g_fc[t] == c_water * m_fc_lb * (t_fc[t] - t_de[t]))
        # model.addCons(g_fc[t] * (1-z_fc[t]) == c_water * m_fc_lb * (t_fc[t] - t_de[t]))
        model.addCons(p_pump_fc[t] == eta_pump_fc * m_fc_lb)

        # PV
        model.addCons(p_pv[t] == eta_pv * p_pv_max * pv_gen[t])

        # PIPE
        model.addCons(g_load[t] == c_water * m_de_lb * (t_supply[t] - t_de[t])) #// + eta_pipe_loss * (t_supply[t] - t_env[t]))
        model.addCons(p_pump_pipe[t] == eta_pump_pipe * m_de_lb)

    # BS
    for t in range(period-1):
        model.addCons(p_bs_sto[t + 1] - p_bs_sto[t] == p_bs_ch[t] - p_bs_dis[t])
    model.addCons(p_bs_sto[0] == bsSocRT)
    #// model.addCons(p_bs_sto[0] - p_bs_sto[-1] == p_bs_ch[-1] - p_bs_dis[-1])
    model.addCons(p_bs_sto[0] == p_bs_ch[-1])


    # HT
    for t in range(period-1):
        model.addCons(z_ghp_ht[t] * g_ghp_ht[t] + z_eb[t] * g_eb_ht[t] - g_ht[t]
                           == c_water * m_ht_sto * (t_ht_sto[t + 1] - t_ht_sto[t]) + eta_ht_loss * (t_ht_sto[t] - t_env[t]))
        # model.addCons(z_ghp_ht[t] * g_ghp_ht[t] + z_eb[t] * g_eb_ht[t] + z_fc[t] * g_fc_ht[t] - g_ht[t]
        #                    == c_water * m_ht_sto * (t_ht_sto[t + 1] - t_ht_sto[t]) + eta_ht_loss * (t_ht_sto[t] - t_env[t]))
    #// model.addConstrs(z_ghp_ht[t]*g_ghp_ht[t] + z_eb_ht[t]*g_eb_ht[t] + z_fc_ht[t]*g_fc_ht[t] - g_ht[t]
    #//                  == c_water * m_ht_sto * (t_ht_sto[t + 1] - t_ht_sto[t]) + eta_ht_loss * (t_ht_sto[t] - t_env[t])
    #//                  for t in range(period - 1))
    model.addCons(t_ht_sto[0] == htTemperatureRT)  # 储热罐初始温度
    model.addCons(t_ht_sto[-1] == t_ht_sto[0])  # 储热罐首尾相连
    #// model.addCons(z_ghp_ht[-1]*g_ghp_ht[-1] + z_eb[-1]*g_eb_ht[-1] + z_fc[-1]*g_fc_ht[-1] - g_ht[-1]
    #//               == c_water * m_ht_sto * (t_ht_sto[0] - t_ht_sto[-1]) + eta_ht_loss * (t_ht_sto[-1] - t_env[23]))
    for t in range(period):
        model.addCons(g_ht[t] == c_water * m_ht_lb * (t_ht[t] - t_de[t]))
    #// model.addConstrs(p_pump_ht[t] == eta_pump_ht * m_ht[t] for t in range(period))

    # opex
    for t in range(period):
        model.addCons(opex_t[t] == hydrogen_price * h_pur[t] + lambda_ele_in[t] * p_pur[t])
    model.addCons(opex == opt.quicksum(opex_t[t] for t in range(period)))  # 总运行成本
    model.setObjective(opex, sense="minimize")

    model.setParam("limits/time", 100)  # 设置时间限制为200秒
    model.setParam('heuristics/feaspump/freq', 1)        # 频繁调用可行性泵

    '''
        执行优化
    '''
    try:
        model.optimize()

        status = model.getStatus()
        print("求解状态:", status)

        if status == "optimal":
            # 最优解已找到
            print("找到了最优解")
            print("目标值:", model.getObjVal())
            respCode = RespCode.SuccessState.value  # 最优解
        elif status == "timelimit":
            # 求解因超时终止，需检查是否有可行解
            n_sols = model.getNSols()
            if n_sols > 0:
                print("在时间限制内找到了可行解（非最优）")
                print("当前最佳可行解的目标值:", model.getObjVal())
                respCode = RespCode.TimelimitState.value  # 超时但有解
            else:
                print("在时间限制内未找到任何可行解")
                respCode = RespCode.InfeasibleState.value
        elif status == "infeasible":
            # 模型无可行解
            print("模型不可行：没有满足所有约束的解")
            respCode = RespCode.InfeasibleState.value

        else:
            print(f"求解器返回其他状态: {status}")
            respCode = RespCode.ErrorState.value
        _logging.info("求解完成,求解器状态为: {},resCode: {}".format(status, respCode))
    except Exception as E:
        handle_error("求解过程中发生异常", E)
        print(
            {
                "status": "error",
                "error_type": type(E).__name__,
                "error_message": str(E)
            }
        )

    # TODO: 处理优化结果,输出
    '''
        读取优化变量值，写入<dict_control>字典
    '''
    dict_control = {
        "opex": model.getVal(opex),
        "opex_t": [model.getVal(opex_t[t]) for t in range(period)],
        
        "z_pur": [model.getVal(z_pur[t]) for t in range(period)],
        "z_ghp_de": [model.getVal(z_ghp_de[t]) for t in range(period)],
        "z_ghp_ht": [model.getVal(z_ghp_ht[t]) for t in range(period)],
        "z_eb": [model.getVal(z_eb[t]) for t in range(period)],
        "z_ht_sto": [model.getVal(z_ht_sto[t]) for t in range(period)],
        "p_pv": [model.getVal(p_pv[t]) for t in range(period)],
        "p_pur": [model.getVal(p_pur[t]) for t in range(period)],
        "h_pur": [model.getVal(h_pur[t]) for t in range(period)],
        "t_de": [model.getVal(t_de[t]) for t in range(period)],
        "t_supply": [model.getVal(t_supply[t]) for t in range(period)],
        "p_ghp": [
            (model.getVal(z_ghp_de[t]) + model.getVal(z_ghp_ht[t])) * p_ghp_max
            for t in range(period)
        ],
        "g_ghp": [model.getVal(g_ghp[t]) for t in range(period)],
        "g_ghp_ht": [model.getVal(g_ghp_ht[t]) for t in range(period)],
        "g_ghp_de": [model.getVal(g_ghp_de[t]) for t in range(period)],
        "t_ghp": [model.getVal(t_ghp[t]) for t in range(period)],
        "p_pump_ghp": [model.getVal(p_pump_ghp[t]) for t in range(period)],
        "p_eb": [model.getVal(p_eb[t]) for t in range(period)],
        "g_eb": [model.getVal(g_eb[t]) for t in range(period)],
        "g_eb_ht": [model.getVal(g_eb_ht[t]) for t in range(period)],
        "g_eb_de": [model.getVal(g_eb_de[t]) for t in range(period)],
        "t_eb": [model.getVal(t_eb[t]) for t in range(period)],
        "p_ahp": [model.getVal(p_ahp[t]) for t in range(period)],
        "g_ahp": [model.getVal(g_ahp[t]) for t in range(period)],
        "t_ahp": [model.getVal(t_ahp[t]) for t in range(period)],
        "m_h_fc": [model.getVal(m_h_fc[t]) for t in range(period)],
        "p_fc": [model.getVal(p_fc[t]) for t in range(period)],
        "g_fc": [model.getVal(g_fc[t]) for t in range(period)],
        "t_fc": [model.getVal(t_fc[t]) for t in range(period)],
        "g_ht": [model.getVal(g_ht[t]) for t in range(period)],
        "t_ht_sto": [model.getVal(t_ht_sto[t]) for t in range(period)],
        "t_ht": [model.getVal(t_ht[t]) for t in range(period)],
        "p_bs_sto": [model.getVal(p_bs_sto[t]) for t in range(period)],
        "p_bs_ch": [model.getVal(p_bs_ch[t]) for t in range(period)],
        "p_bs_dis": [model.getVal(p_bs_dis[t]) for t in range(period)],
    }
    # to_csv(dict_control, "ori_{}".format(round(2724 * TEST_ALF, 0))) # ! 测试使用
    # 修正输出
    dict_control = output_CleanAndProcess(dict_control)
    # to_csv(dict_control, "after_{}".format(round(2724 * TEST_ALF, 0)))
    for id in dict_control["procedureID"]:
        if id == 'None':
            _logging.info("负荷{}下存在None流程".format(round(2724 * TEST_ALF, 0)))
            to_csv(dict_control, "{}".format(round(2724 * TEST_ALF, 0))) # ! 测试使用
            break
    _logging.info("负荷{}下gap值为: {}".format(round(2724 * TEST_ALF, 0), model.getGap()))      
    
    '''
        输出信息包括未来1h控制量：
        - 响应状态码
        - 优化目标值
        - 操纵变量值
        - 流程ID
    '''

    currentProcedureID = dict_control["procedureID"][0]
    # currentProcedureID = 'None' # ! 测试匹配功能使用使用
    if currentProcedureID == 'None':
        _logging.info("{}:当前调度流程ID为None,需要匹配到示例流程".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        print("{}:当前调度流程ID为None,需要匹配到示例流程".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        '''
            -调取24小时负荷预测数据和最大值
            -按负荷匹配示例流程输出热负荷:2000 2700 3500kw
        '''
        heatingLoadMax = max(g_load)
        EPS = 1e-8
        exampleHeatLoad = min(v := [2000, 2700, 3500], key=lambda v: abs(heatingLoadMax - v) / (abs(heatingLoadMax) + EPS)) # 相对最接近
        # 读取exampleHeatLoad.xls中的数据作为输出
        example_data = pd.read_excel('basicStrategy/{}.xls'.format(exampleHeatLoad))
        currentProcedureID = int(example_data['procedureID'][currentHour])
        _logging.info("{}:匹配到示例流程: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),currentProcedureID))
        print("{}:匹配到示例流程: {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),currentProcedureID))
        respCode = RespCode.ProcedureLack.value  # 流程缺失，匹配示例流程输出
        output_data = build_output(
            respCode=respCode,
            objectiveValue=model.getObjVal(),
            dict_control=example_data,
            currentTimeStamp=currentTimeStamp
        )
    else:
        output_data = build_output(
            respCode=respCode,
            objectiveValue=model.getObjVal(),
            dict_control=dict_control,
            currentTimeStamp=currentTimeStamp
        )
    

    return output_data

def main(data, config):

    return Optimization(data, config)





# ! 测试用
if __name__ == "__main__":
    

    # 运行优化模型
    '''
    
    '''