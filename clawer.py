# -*- coding: utf-8 -*-
import os
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from xml.dom import minidom

# 1. 干净的频道列表（已包含您整理的全部核心 ID，并映射了中文标准台名）
CHANNELS = {
    "cctv1": "CCTV-1 综合",
    "cctv2": "CCTV-2 财经",
    "cctv3": "CCTV-3 综艺",
    "cctv4": "CCTV-4 中文国际(亚)",
    "cctv5": "CCTV-5 体育",
    "cctv5plus": "CCTV-5+ 体育赛事",
    "cctv6": "CCTV-6 电影",
    "cctv7": "CCTV-7 国防军事",
    "cctv8": "CCTV-8 电视剧",
    "cctvjilu": "CCTV-9 纪录",
    "cctv10": "CCTV-10 科教",
    "cctv11": "CCTV-11 戏曲",
    "cctv12": "CCTV-12 社会与法",
    "cctv13": "CCTV-13 新闻",
    "cctvchild": "CCTV-14 少儿",
    "cctv15": "CCTV-15 音乐",
    "cctv16": "CCTV-16 奥林匹克",
    "cctv17": "CCTV-17 农业农村",
    "cctveurope": "CCTV-4 中文国际(欧)",
    "cctvamerica": "CCTV-4 中文国际(美)"
}

def get_date_list():
    """获取今天、明天、后天的日期列表 (格式: YYYYMMDD)"""
    today = datetime.now()
    return [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]

def format_xmltv_time(date_str, time_str):
    """将日期(YYYYMMDD)和时间(HH:MM)转换为 XMLTV 标准时间格式 (YYYYMMDDHHMMSS +0800)"""
    if not time_str:
        return ""
    time_part = time_str.strip()[:5].replace(":", "")
    if len(time_part) == 4:
        return f"{date_str}{time_part}00 +0800"
    return ""

def fetch_epg_data():
    """从央视接口循环抓取数据并解析为内部统一结构"""
    dates = get_date_list()
    # 结构初始化: { channel_id: [ {title, start_raw, end_raw}, ... ] }
    epg_database = {ch: [] for ch in CHANNELS}

    for date in dates:
        print(f"正在抓取 {date} 的节目数据...")
        for ch in CHANNELS:
            # 优化点：强制请求纯 JSON 格式
            url = f"https://api.cntv.cn/epg/getEpgInfoByChannelNew?c={ch}&serviceId=tvcctv&d={date}&t=json"
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                res_data = response.json()
                
                program_list = res_data.get("data", {}).get(ch, {}).get("list", [])
                
                for prog in program_list:
                    title = prog.get("title", "未知节目")
                    start_time = prog.get("showTime", "")
                    
                    if start_time:
                        xml_start = format_xmltv_time(date, start_time)
                        epg_database[ch].append({
                            "title": title,
                            "start_raw": xml_start,
                            "end_raw": ""  # 占位，稍后统一计算
                        })
            except Exception as e:
                print(f"  ❌ 频道 {ch} 在 {date} 抓取失败: {e}")
            time.sleep(0.2)  # 温和延迟，防止请求过快被服务器临时阻断
            
    # 核心算法：利用下一条节目的开始时间补齐当前节目的结束时间
    for ch, programs in epg_database.items():
        if not programs:
            continue
        # 按时间正序排列
        programs.sort(key=lambda x: x["start_raw"])
        
        for i in range(len(programs) - 1):
            programs[i]["end_raw"] = programs[i+1]["start_raw"]
            
        # 给最后三天最后一条节目单一个兜底的结束时间（往后顺延 2 小时）
        if programs:
            last_start = programs[-1]["start_raw"][:14]
            try:
                dt = datetime.strptime(last_start, "%Y%m%d%H%M%S")
                dt_end = dt + timedelta(hours=2)
                programs[-1]["end_raw"] = dt_end.strftime("%Y%m%d%H%M%S") + " +0800"
            except:
                programs[-1]["end_raw"] = programs[-1]["start_raw"]

    return epg_database

def generate_xmltv(epg_database, filename="cctv_epg.xml"):
    """将整合后的数据转换为标准的 XMLTV 树状结构并格式化输出"""
    root = ET.Element("tv")
    root.set("generator-info-name", "CNTV EPG Downloader")
    root.set("generator-info-url", "https://api.cntv.cn")

    # 1. 创建 <channel> 节点
    for ch_id, ch_name in CHANNELS.items():
        channel_node = ET.SubElement(root, "channel", id=ch_id)
        display_name = ET.SubElement(channel_node, "display-name")
        display_name.text = ch_name

    # 2. 创建 <programme> 节点
    for ch_id, programs in epg_database.items():
        for prog in programs:
            if not prog["start_raw"] or not prog["end_raw"]:
                continue
            prog_node = ET.SubElement(root, "programme", 
                                      start=prog["start_raw"], 
                                      stop=prog["end_raw"], 
                                      channel=ch_id)
            
            title_node = ET.SubElement(prog_node, "title", lang="zh")
            title_node.text = prog["title"]

    # 3. 使用 minidom 美化缩进，使 XML 易读且体积小
    xml_str = ET.tostring(root, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_str)
    pretty_xml = parsed_xml.toprettyxml(indent="  ", encoding="utf-8")

    with open(filename, "wb") as f:
        f.write(pretty_xml)
        
    print(f"\n🎉 完美！XMLTV 文件已成功生成 -> {os.path.abspath(filename)}")

if __name__ == "__main__":
    start_run = time.time()
    # 1. 抓取与合并
    data = fetch_epg_data()
    # 2. 生成规范 XML 文件
    generate_xmltv(data, "cctv_epg.xml")
    print(f"总运行耗时: {time.time() - start_run:.2f} 秒")
