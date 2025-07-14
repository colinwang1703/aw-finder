import requests
import schedule
import time
import datetime

from flask import Flask, jsonify, request

from rich import print

# 配置部分
BASE_URL = "http://localhost:5600/api/0"
BUCKET_ID = "aw-watcher-window_LAPTOP-PFKAKGVO"  # 按你的bucket名填写
INTERVAL = 3  # 间隔秒数

# Flask应用配置
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # 支持中文显示

def fetch_recent_window_events():
    """获取最近的窗口事件数据"""
    url = f"{BASE_URL}/buckets/{BUCKET_ID}/events"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        events = resp.json()
        print(f"[{datetime.datetime.now()}] 最近1小时窗口事件数: {len(events)}")
        return events
    except Exception as e:
        print(f"[{datetime.datetime.now()}] 获取数据出错: {e}")
        return []

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
    events = fetch_recent_window_events_api()
    stats = get_window_stats(events)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>窗口使用情况统计</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
            .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }}
            .app-list {{ margin-top: 20px; }}
            .app-item {{ background: #fff; margin: 10px 0; padding: 15px; border-radius: 5px; border: 1px solid #ddd; }}
            .app-name {{ font-weight: bold; font-size: 1.1em; color: #333; }}
            .app-details {{ margin-top: 5px; color: #666; }}
            .progress-bar {{ background: #e9ecef; height: 20px; border-radius: 10px; margin: 10px 0; }}
            .progress-fill {{ background: #007bff; height: 100%; border-radius: 10px; transition: width 0.3s ease; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🖥️ 窗口使用情况统计</h1>
                <p>最后更新时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <h3>📊 总事件数</h3>
                    <h2>{stats.get('total_events', 0)}</h2>
                </div>
                <div class="stat-card">
                    <h3>⏱️ 总时长</h3>
                    <h2>{round(stats.get('total_duration', 0) / 60, 2)} 分钟</h2>
                </div>
                <div class="stat-card">
                    <h3>📱 应用数量</h3>
                    <h2>{len(stats.get('app_usage', {}))}</h2>
                </div>
            </div>
            
            <div class="app-list">
                <h2>应用使用详情</h2>
    """
    
    # 按使用时长排序
    app_usage = stats.get('app_usage', {})
    sorted_apps = sorted(app_usage.items(), key=lambda x: x[1]['total_duration'], reverse=True)
    
    for app_name, data in sorted_apps:
        duration_minutes = round(data['total_duration'] / 60, 2)
        percentage = data['percentage']
        
        html += f"""
                <div class="app-item">
                    <div class="app-name">{app_name}</div>
                    <div class="app-details">
                        使用时长: {duration_minutes} 分钟 ({percentage}%) | 切换次数: {data['count']}
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {percentage}%"></div>
                    </div>
                    <details>
                        <summary>窗口标题 ({len(data['titles'])}个)</summary>
                        <ul>
        """
        
        for title in data['titles'][:10]:  # 只显示前10个标题
            html += f"<li>{title}</li>"
        
        if len(data['titles']) > 10:
            html += f"<li>... 还有 {len(data['titles']) - 10} 个标题</li>"
        
        html += """
                        </ul>
                    </details>
                </div>
        """
    
    html += """
            </div>
        </div>
        <script>
            // 自动刷新页面
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """
    
    return html

@app.route('/api/events')
def api_events():
    """API接口：获取原始事件数据"""
    events = fetch_recent_window_events_api()
    return jsonify({
        'success': True,
        'data': events,
        'timestamp': datetime.datetime.now().isoformat()
    })

@app.route('/api/stats')
def api_stats():
    """API接口：获取统计数据"""
    events = fetch_recent_window_events_api()
    stats = get_window_stats(events)
    return jsonify({
        'success': True,
        'data': stats,
        'timestamp': datetime.datetime.now().isoformat()
    })

def fetch_recent_window_events_api():
    """为API调用获取窗口事件数据（不打印日志）"""
    url = f"{BASE_URL}/buckets/{BUCKET_ID}/events"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[{datetime.datetime.now()}] API获取数据出错: {e}")
        return []

# 启动定时任务和Web服务
def start_scheduler():
    """在后台运行定时任务"""
    import threading
    
    def run_scheduler():
        print(f"定时获取 {BUCKET_ID} 最近1小时窗口使用记录，每{INTERVAL}秒一次。")
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
    print("🔗 API接口:")
    print("   - http://localhost:5000/api/events (原始事件数据)")
    print("   - http://localhost:5000/api/stats (统计数据)")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
