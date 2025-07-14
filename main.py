import requests
import schedule
import time
import datetime
import os


from flask import Flask, jsonify, request
from datetime import datetime, timedelta

from rich import print
from dotenv import load_dotenv

load_dotenv()

if os.getenv("DEBUG") == "True":
    # 配置部分
    BASE_URL = "http://localhost:5600/api/0"
    BUCKET_ID = "aw-watcher-window_LAPTOP-PFKAKGVO"  # 按你的bucket名填写
    INTERVAL = 5  # 间隔秒数
else:
    # 生产环境配置
    BASE_URL = "http://192.168.0.156:5600/api/0"
    BUCKET_ID = "aw-watcher-window_LAPTOP-PFKAKGVO"
    INTERVAL = 120  # 间隔秒数

# Flask应用配置
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 支持中文显示

def fetch_recent_window_events():
    """获取最近的窗口事件数据"""
    url = f"{BASE_URL}/buckets/{BUCKET_ID}/events"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        events = resp.json()
        print(f"[{datetime.now()}] 最近1小时窗口事件数: {len(events)}")
        return events
    except requests.exceptions.ConnectionError:
        print(f"[{datetime.now()}] ActivityWatch服务未运行，无法获取数据。")
        pass
    except requests.exceptions.Timeout:
        print(f"[{datetime.now()}] 请求超时，无法获取数据。")
        pass
    except Exception as e:
        print(f"[{datetime.now()}] 获取数据出错: {e}")
        pass
    return []

def fetch_window_events_by_timerange(hours=1):
    """根据时间范围获取窗口事件数据"""
    from datetime import timezone
    
    # 使用UTC时间，因为ActivityWatch内部使用UTC
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    # 转换为ISO格式，ActivityWatch API需要的格式
    start_iso = start_time.isoformat()
    end_iso = end_time.isoformat()
    
    url = f"{BASE_URL}/buckets/{BUCKET_ID}/events"
    params = {
        'start': start_iso,
        'end': end_iso
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        events = resp.json()
        print(f"[DEBUG] 请求时间范围: {start_iso} 到 {end_iso}")
        print(f"[DEBUG] 获取到 {len(events)} 个事件")
        return events
    except requests.exceptions.ConnectionError:
        # ActivityWatch服务未运行时静默处理
        return []
    except requests.exceptions.Timeout:
        # 请求超时时静默处理
        return []
    except Exception:
        # 其他错误也静默处理
        return []

def fetch_window_events_by_timerange_alternative(hours=1):
    """备用方案：使用本地时间但尝试不同的API调用方式"""
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    url = f"{BASE_URL}/buckets/{BUCKET_ID}/events"
    
    # 尝试方案1：不使用时间参数，获取所有数据然后在本地筛选
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        all_events = resp.json()
        
        # 在本地筛选符合时间范围的事件
        filtered_events = []
        parse_errors = 0
        time_range_debug = []
        
        for event in all_events:
            # ActivityWatch事件的时间戳格式可能是字符串
            event_time_str = event.get('timestamp')
            if event_time_str:
                try:
                    # 使用安全的时间解析函数
                    event_time = parse_timestamp_safe(event_time_str)
                    if event_time is None:
                        continue
                    
                    # 转换为本地时间进行比较
                    if hasattr(event_time, 'tzinfo') and event_time.tzinfo:
                        event_time_local = event_time.astimezone()
                    else:
                        event_time_local = event_time
                    
                    # 移除时区信息以便比较
                    event_time_naive = event_time_local.replace(tzinfo=None)
                    
                    # 检查事件是否在时间范围内
                    if start_time <= event_time_naive <= end_time:
                        filtered_events.append(event)
                    
                    # 收集调试信息（只收集前5个）
                    if len(time_range_debug) < 5:
                        time_range_debug.append({
                            'original': event_time_str,
                            'parsed': event_time.isoformat() if event_time else 'None',
                            'local_naive': event_time_naive.isoformat(),
                            'in_range': start_time <= event_time_naive <= end_time
                        })
                    
                except Exception as e:
                    parse_errors += 1
                    if parse_errors <= 3:  # 只打印前3个错误
                        print(f"[DEBUG] 时间解析错误: {event_time_str} -> {e}")
                    continue
        
        print(f"[DEBUG] 备用方案详情:")
        print(f"  - 目标时间范围: {start_time} 到 {end_time}")
        print(f"  - 解析错误数: {parse_errors}")
        print(f"  - 筛选结果: 从 {len(all_events)} 个事件中筛选出 {len(filtered_events)} 个")
        
        # 打印一些时间范围调试信息
        for debug_item in time_range_debug:
            print(f"  - 时间样本: {debug_item}")
        
        return filtered_events
        
    except Exception as e:
        print(f"[DEBUG] 备用方案异常: {e}")
        return []

def fetch_window_events_by_timerange_smart(hours=1):
    """智能获取窗口事件：先尝试UTC时间，失败后尝试备用方案"""
    # 首先尝试UTC时间方案
    events = fetch_window_events_by_timerange(hours)
    
    # 如果没有获取到数据，尝试备用方案
    if not events:
        print(f"[DEBUG] UTC时间方案无数据，尝试备用方案...")
        events = fetch_window_events_by_timerange_alternative(hours)
    
    return events

def get_window_stats(events):
    """分析窗口使用统计"""
    if not events:
        return {}
    
    app_usage = {}
    total_duration = 0
    
    for event in events:
        data = event.get('data', {})
        app_name = data.get('app', 'Unknown')
        title = data.get('title', 'Unknown')
        duration = event.get('duration', 0)
        
        if app_name not in app_usage:
            app_usage[app_name] = {
                'total_duration': 0,
                'count': 0,
                'titles': set()
            }
        
        app_usage[app_name]['total_duration'] += duration
        app_usage[app_name]['count'] += 1
        app_usage[app_name]['titles'].add(title)
        total_duration += duration
    
    # 转换为可序列化的格式
    for app in app_usage:
        app_usage[app]['titles'] = list(app_usage[app]['titles'])
        app_usage[app]['percentage'] = round((app_usage[app]['total_duration'] / total_duration * 100), 2) if total_duration > 0 else 0
    
    return {
        'total_events': len(events),
        'total_duration': total_duration,
        'app_usage': app_usage
    }

@app.route('/')
def index():
    """主页面，显示使用统计概览"""
    # 获取时间范围参数，默认1小时
    hours = request.args.get('hours', 1, type=int)
    
    # 限制时间范围在合理区间内
    if hours not in [1, 6, 24, 72, 168]:  # 1小时, 6小时, 1天, 3天, 7天
        hours = 1
    
    events = fetch_window_events_by_timerange_smart(hours)
    stats = get_window_stats(events)
    
    # 根据时间范围显示不同的标题
    time_labels = {
        1: "1小时",
        6: "6小时", 
        24: "1天",
        72: "3天",
        168: "7天"
    }
    
    current_time_label = time_labels.get(hours, f"{hours}小时")
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>窗口使用情况统计 - {current_time_label}</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .time-filter {{ text-align: center; margin-bottom: 20px; }}
            .time-btn {{ display: inline-block; margin: 0 5px; padding: 8px 16px; background: #f8f9fa; border: 1px solid #ddd; border-radius: 20px; text-decoration: none; color: #333; transition: all 0.3s; }}
            .time-btn:hover {{ background: #e9ecef; }}
            .time-btn.active {{ background: #007bff; color: white; border-color: #007bff; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
            .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }}
            .app-list {{ margin-top: 20px; }}
            .app-item {{ background: #fff; margin: 10px 0; padding: 15px; border-radius: 5px; border: 1px solid #ddd; }}
            .app-name {{ font-weight: bold; font-size: 1.1em; color: #333; }}
            .app-details {{ margin-top: 5px; color: #666; }}
            .progress-bar {{ background: #e9ecef; height: 20px; border-radius: 10px; margin: 10px 0; }}
            .progress-fill {{ background: #007bff; height: 100%; border-radius: 10px; transition: width 0.3s ease; }}
            .no-data {{ text-align: center; padding: 40px; color: #666; background: #f8f9fa; border-radius: 5px; margin: 20px 0; }}
            .status-indicator {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; }}
            .status-online {{ background: #28a745; }}
            .status-offline {{ background: #dc3545; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🖥️ 窗口使用情况统计</h1>
                <p>
                    <span class="status-indicator {'status-online' if events else 'status-offline'}"></span>
                    {'ActivityWatch 服务运行中' if events else 'ActivityWatch 服务未运行'}
                    | 最后更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </p>
            </div>
            
            <div class="time-filter">
                <h3>📅 选择时间范围：</h3>
                <a href="?hours=1" class="time-btn {'active' if hours == 1 else ''}">📊 1小时</a>
                <a href="?hours=6" class="time-btn {'active' if hours == 6 else ''}">⏰ 6小时</a>
                <a href="?hours=24" class="time-btn {'active' if hours == 24 else ''}">📅 1天</a>
                <a href="?hours=72" class="time-btn {'active' if hours == 72 else ''}">📈 3天</a>
                <a href="?hours=168" class="time-btn {'active' if hours == 168 else ''}">📆 7天</a>
            </div>
    """
    
    if not events:
        html += """
            <div class="no-data">
                <h3>🔌 暂无数据</h3>
                <p>ActivityWatch 服务可能未运行，或者所选时间段内没有窗口活动记录。</p>
                <p>请确保 ActivityWatch 正在运行，并稍后刷新页面。</p>
            </div>
        """
    else:
        total_hours = round(stats.get('total_duration', 0) / 3600, 2)
        total_minutes = round(stats.get('total_duration', 0) / 60, 2)
        
        html += f"""
            <div class="stats">
                <div class="stat-card">
                    <h3>📊 总事件数</h3>
                    <h2>{stats.get('total_events', 0)}</h2>
                </div>
                <div class="stat-card">
                    <h3>⏱️ 活跃时长</h3>
                    <h2>{total_hours} 小时</h2>
                    <small>({total_minutes} 分钟)</small>
                </div>
                <div class="stat-card">
                    <h3>📱 应用数量</h3>
                    <h2>{len(stats.get('app_usage', {}))}</h2>
                </div>
                <div class="stat-card">
                    <h3>📋 时间段</h3>
                    <h2>{current_time_label}</h2>
                    <small>过去 {current_time_label} 的数据</small>
                </div>
            </div>
            
            <div class="app-list">
                <h2>应用使用详情 (过去{current_time_label})</h2>
        """
        
        # 按使用时长排序
        app_usage = stats.get('app_usage', {})
        sorted_apps = sorted(app_usage.items(), key=lambda x: x[1]['total_duration'], reverse=True)
        
        if sorted_apps:
            for app_name, data in sorted_apps:
                duration_hours = round(data['total_duration'] / 3600, 2)
                duration_minutes = round(data['total_duration'] / 60, 2)
                percentage = data['percentage']
                
                html += f"""
                        <div class="app-item">
                            <div class="app-name">{app_name}</div>
                            <div class="app-details">
                                使用时长: {duration_hours} 小时 ({duration_minutes} 分钟) | 占比: {percentage}% | 切换次数: {data['count']}
                            </div>
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: {percentage}%"></div>
                            </div>
                            <details>
                                <summary>窗口标题 ({len(data['titles'])}个)</summary>
                                <ul>
                """
                
                for title in data['titles'][:15]:  # 显示前15个标题
                    html += f"<li>{title}</li>"
                
                if len(data['titles']) > 15:
                    html += f"<li>... 还有 {len(data['titles']) - 15} 个标题</li>"
                
                html += """
                                </ul>
                            </details>
                        </div>
                """
        else:
            html += """
                <div class="no-data">
                    <p>所选时间段内没有应用使用记录</p>
                </div>
            """
        
        html += "</div>"
    
    html += """
        </div>
        <script>
            // 自动刷新页面，但保持当前选择的时间范围
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """
    
    return html

@app.route('/api/events')
def api_events():
    """API接口：获取原始事件数据"""
    hours = request.args.get('hours', 1, type=int)
    if hours not in [1, 6, 24, 72, 168]:
        hours = 1
    
    events = fetch_window_events_by_timerange_smart(hours)
    return jsonify({
        'success': True,
        'data': events,
        'hours': hours,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/stats')
def api_stats():
    """API接口：获取统计数据"""
    hours = request.args.get('hours', 1, type=int)
    if hours not in [1, 6, 24, 72, 168]:
        hours = 1
    
    events = fetch_window_events_by_timerange_smart(hours)
    stats = get_window_stats(events)
    return jsonify({
        'success': True,
        'data': stats,
        'hours': hours,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/debug/time')
def debug_time():
    """调试时间信息"""
    from datetime import timezone
    
    now_local = datetime.now()
    now_utc = datetime.now(timezone.utc)
    
    debug_info = {
        'local_time': now_local.isoformat(),
        'utc_time': now_utc.isoformat(),
        'timezone_offset': str(now_local - now_utc.replace(tzinfo=None)),
        'test_1h_local': (now_local - timedelta(hours=1)).isoformat(),
        'test_1h_utc': (now_utc - timedelta(hours=1)).isoformat(),
    }
    
    return jsonify(debug_info)

@app.route('/debug/events')
def debug_events():
    """调试事件数据格式"""
    url = f"{BASE_URL}/buckets/{BUCKET_ID}/events"
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        all_events = resp.json()
        
        # 分析前几个事件的时间戳格式
        sample_events = all_events[:5] if all_events else []
        
        debug_info = {
            'total_events': len(all_events),
            'sample_events': []
        }
        
        for i, event in enumerate(sample_events):
            event_info = {
                'index': i,
                'timestamp': event.get('timestamp'),
                'duration': event.get('duration'),
                'data': event.get('data', {}),
                'timestamp_type': type(event.get('timestamp')).__name__
            }
            
            # 尝试解析时间戳
            timestamp_str = event.get('timestamp')
            if timestamp_str:
                try:
                    from dateutil import parser
                    parsed_time = parser.parse(timestamp_str)
                    event_info['parsed_timestamp'] = parsed_time.isoformat()
                    event_info['parsed_timezone'] = str(parsed_time.tzinfo)
                except Exception as e:
                    event_info['parse_error'] = str(e)
            
            debug_info['sample_events'].append(event_info)
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)})

def fetch_recent_window_events_api():
    """为API调用获取窗口事件数据（不打印日志）- 保持向后兼容"""
    return fetch_window_events_by_timerange_smart(1)

# 启动定时任务和Web服务
def start_scheduler():
    """在后台运行定时任务"""
    import threading
    
    def run_scheduler():
        print(f"定时获取 {BUCKET_ID} 最近1小时窗口使用记录，每{INTERVAL}秒一次。")
        print("如果 ActivityWatch 服务未运行，将自动忽略错误。")
        while True:
            schedule.run_pending()
            time.sleep(1)
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

if __name__ == '__main__':
    # 安排定时任务
    schedule.every(INTERVAL).seconds.do(fetch_recent_window_events)
    
    # 启动后台定时任务
    start_scheduler()
    
    # 启动Flask Web服务
    print("🚀 启动Web服务器...")
    print("📊 访问 http://localhost:5000 查看使用统计")
    print("🔗 API接口 (支持 ?hours=1|6|24|72|168 参数):")
    print("   - http://localhost:5000/api/events (原始事件数据)")
    print("   - http://localhost:5000/api/stats (统计数据)")
    print("⏰ 时间筛选: 1小时/6小时/1天/3天/7天")
    print("🔌 如果 ActivityWatch 未运行，错误将被自动忽略")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
