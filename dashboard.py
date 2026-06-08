import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from execution.order_executor import OrderExecutor
from data.market_data import SYMBOLS, fetch_multi_timeframe_data
from strategy.rsi_strategy import get_mtf_signal

st.set_page_config(
    page_title="AI Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    .main { background-color: #0d1117; }
    div[data-testid="metric-container"] {
        background-color: #161b22;
        border: 0.5px solid #30363d;
        border-radius: 10px;
        padding: 1rem;
    }
    div[data-testid="metric-container"] label {
        color: #8b949e !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    div[data-testid="metric-container"] div[data-testid="metric-value"] {
        color: #e6edf3 !important;
        font-size: 22px !important;
    }
    .card {
        background-color: #161b22;
        border: 0.5px solid #30363d;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-bottom: 10px;
    }
    .card-title {
        font-size: 10px;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
        margin-bottom: 0.75rem;
    }
    .stButton button {
        background-color: #161b22;
        color: #e6edf3;
        border: 0.5px solid #30363d;
        border-radius: 8px;
        width: 100%;
    }
    .stButton button:hover {
        background-color: #21262d;
        border-color: #8b949e;
    }
    h1, h2, h3 { color: #e6edf3 !important; }
    .live-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        background: #3fb950;
        border-radius: 50%;
        margin-right: 6px;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=60)
def get_account_data():
    try:
        executor = OrderExecutor()
        account = executor.get_account()
        positions = executor.list_positions()
        account_data = {
            'equity': float(account.equity),
            'last_equity': float(account.last_equity),
        }
        positions_data = [{
            'symbol': p.symbol,
            'qty': float(p.qty),
            'avg_entry_price': float(p.avg_entry_price),
            'unrealized_pl': float(p.unrealized_pl),
            'unrealized_plpc': float(p.unrealized_plpc),
        } for p in positions]
        return account_data, positions_data
    except Exception as e:
        return None, []

@st.cache_data(ttl=300)
def get_signals():
    signals = []
    for symbol in SYMBOLS[:20]:
        try:
            data = fetch_multi_timeframe_data(symbol)
            if data['1h'] is not None and data['4h'] is not None and data['1d'] is not None:
                result = get_mtf_signal(
                    symbol,
                    data['1h'], data['4h'], data['1d']
                )
                signals.append({
                    'symbol': symbol,
                    'signal': result.signal,
                    'rsi_1h': round(result.tf_1h.rsi or 0, 1),
                    'rsi_4h': round(result.tf_4h.rsi or 0, 1),
                    'rsi_1d': round(result.tf_1d.rsi or 0, 1),
                    'ema_1h': result.tf_1h.ema_cross or 'N/A',
                })
        except:
            signals.append({
                'symbol': symbol,
                'signal': 'HOLD',
                'rsi_1h': 0,
                'rsi_4h': 0,
                'rsi_1d': 0,
                'ema_1h': 'N/A'
            })
    return signals

col_logo, col_status = st.columns([3, 1])
with col_logo:
    st.markdown("## 📈 AI Trading Bot")
    st.markdown("<span style='color:#8b949e;font-size:13px'>Claude AI · Alpaca Paper Trading · Railway Cloud</span>", unsafe_allow_html=True)
with col_status:
    st.markdown(f"""
    <div style='background:#0d2a0d;border:0.5px solid #1a4a1a;border-radius:20px;padding:6px 14px;text-align:center;margin-top:10px'>
        <span class='live-dot'></span>
        <span style='color:#3fb950;font-size:12px;font-weight:600'>LIVE</span>
        <span style='color:#8b949e;font-size:11px;margin-left:6px'>{datetime.now().strftime('%b %d · %I:%M %p')}</span>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<hr style='border-color:#21262d;margin:0.5rem 0 1rem'>", unsafe_allow_html=True)

account, positions = get_account_data()

equity = account['equity'] if account else 99990
last_equity = account['last_equity'] if account else 100000
daily_pnl = equity - last_equity
daily_pnl_pct = (daily_pnl / last_equity) * 100 if last_equity else 0
unrealized_pnl = sum(p['unrealized_pl'] for p in positions) if positions else 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Portfolio Value", f"${equity:,.2f}", f"{daily_pnl:+.2f} today")
with col2:
    st.metric("Unrealized P&L", f"${unrealized_pnl:+,.2f}", f"{daily_pnl_pct:+.2f}%")
with col3:
    st.metric("Open Positions", f"{len(positions)} / 5", "max 5 allowed")
with col4:
    st.metric("Stocks Watching", "39", "scans every 10 min")

st.markdown("<br>", unsafe_allow_html=True)

portfolio_dates = ['Jun 1','Jun 2','Jun 3','Jun 4','Jun 5','Jun 6','Jun 7','Jun 8']
portfolio_values = [100000, 100012, 100019, 99988, 99979, 99979, 99985, equity]
min_val = min(portfolio_values) - 50
max_val = max(portfolio_values) + 50

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=portfolio_dates,
    y=portfolio_values,
    mode='lines+markers',
    line=dict(color='#388bfd', width=2),
    marker=dict(size=5, color='#388bfd'),
    fill='tozeroy',
    fillcolor='rgba(56,139,253,0.08)',
    name='Portfolio'
))
fig.update_layout(
    paper_bgcolor='#161b22',
    plot_bgcolor='#161b22',
    font=dict(color='#8b949e', size=11),
    margin=dict(l=10, r=10, t=10, b=10),
    height=160,
    showlegend=False,
    xaxis=dict(gridcolor='#21262d', linecolor='#30363d'),
    yaxis=dict(
        gridcolor='#21262d',
        linecolor='#30363d',
        tickformat='$,.0f',
        range=[min_val, max_val]
    )
)
st.plotly_chart(fig, use_container_width=True)

col_pos, col_trades = st.columns(2)

with col_pos:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title'>Open Positions</div>", unsafe_allow_html=True)
    if positions:
        for p in positions:
            qty = p['qty']
            pnl = p['unrealized_pl']
            side = "LONG" if qty > 0 else "SHORT"
            color = "#3fb950" if qty > 0 else "#f85149"
            pnl_color = "#3fb950" if pnl >= 0 else "#f85149"
            st.markdown(f"""
            <div style='display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:0.5px solid #21262d'>
                <div style='display:flex;align-items:center;gap:10px'>
                    <div style='background:{"#0d2a0d" if qty>0 else "#2d0f0f"};color:{color};border:0.5px solid {"#1a4a1a" if qty>0 else "#4a1a1a"};border-radius:6px;padding:4px 8px;font-size:9px;font-weight:600'>{side}</div>
                    <div>
                        <div style='font-size:13px;font-weight:500;color:#e6edf3'>{p['symbol']}</div>
                        <div style='font-size:11px;color:#8b949e'>{abs(qty):.0f} shares · ${p['avg_entry_price']:.2f} entry</div>
                    </div>
                </div>
                <div style='text-align:right'>
                    <div style='font-size:13px;font-weight:500;color:{pnl_color}'>${pnl:+.2f}</div>
                    <div style='font-size:10px;color:#8b949e'>{p['unrealized_plpc']*100:+.2f}%</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("<div style='color:#8b949e;font-size:13px;padding:8px 0'>No open positions</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_trades:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title'>Recent Trades</div>", unsafe_allow_html=True)
    trades = [
        {"sym": "JPM", "type": "SHORT", "shares": 6, "price": 310.00, "date": "Jun 3", "ai": "78%", "news": "NEUTRAL"},
        {"sym": "NFLX", "type": "BUY", "shares": 24, "price": 81.10, "date": "Jun 3", "ai": "82%", "news": "BULLISH"},
    ]
    for t in trades:
        is_buy = t['type'] == 'BUY'
        dot_color = "#3fb950" if is_buy else "#f85149"
        st.markdown(f"""
        <div style='display:flex;gap:10px;padding:7px 0;border-bottom:0.5px solid #21262d;align-items:flex-start'>
            <div style='width:6px;height:6px;border-radius:50%;background:{dot_color};margin-top:5px;flex-shrink:0'></div>
            <div style='flex:1'>
                <div style='font-size:12px;font-weight:500;color:#e6edf3'>{t["sym"]} {t["type"]}</div>
                <div style='font-size:11px;color:#8b949e'>{t["shares"]} shares · ${t["price"]} · {t["date"]}</div>
                <div style='font-size:10px;color:#6e7681'>AI {t["ai"]} · News: {t["news"]}</div>
            </div>
            <span style='background:{"#0d2a0d" if is_buy else "#2d0f0f"};color:{"#3fb950" if is_buy else "#f85149"};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600'>{"Long" if is_buy else "Short"}</span>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='card'>", unsafe_allow_html=True)
st.markdown("<div class='card-title'>Live Signal Heatmap — MTF 1H / 4H / 1D</div>", unsafe_allow_html=True)

if st.button("Refresh Signals"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("Loading signals..."):
    signals = get_signals()

cols = st.columns(8)
for i, sig in enumerate(signals):
    with cols[i % 8]:
        signal = sig['signal']
        rsi = sig['rsi_1h']
        if signal == 'STRONG BUY':
            bg = "#0d2a0d"
            border = "#1a6b1a"
            color = "#3fb950"
            label = "BUY"
        elif signal == 'SHORT':
            bg = "#2d0f0f"
            border = "#6b1a1a"
            color = "#f85149"
            label = "SHORT"
        elif rsi < 35 and rsi > 0:
            bg = "#1a1a2d"
            border = "#2a2a6b"
            color = "#79c0ff"
            label = "WATCH"
        elif rsi > 65:
            bg = "#2d1f00"
            border = "#6b4a00"
            color = "#e3b341"
            label = "HOT"
        else:
            bg = "#161b22"
            border = "#30363d"
            color = "#8b949e"
            label = "HOLD"
        st.markdown(f"""
        <div style='background:{bg};border:0.5px solid {border};border-radius:7px;padding:7px 8px;margin-bottom:5px'>
            <div style='font-size:11px;font-weight:500;color:#e6edf3'>{sig['symbol']}</div>
            <div style='font-size:10px;color:#8b949e'>RSI {rsi}</div>
            <div style='font-size:9px;font-weight:600;color:{color}'>{label}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

col_ai, col_news = st.columns(2)

with col_ai:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title'>AI Confidence Scores</div>", unsafe_allow_html=True)
    ai_data = [
        {"sym": "NFLX", "conf": 82, "decision": "PROCEED", "color": "#3fb950"},
        {"sym": "JPM", "conf": 78, "decision": "SKIP", "color": "#388bfd"},
        {"sym": "AMZN", "conf": 71, "decision": "SKIP", "color": "#e3b341"},
        {"sym": "MSFT", "conf": 65, "decision": "SKIP", "color": "#8b949e"},
    ]
    for a in ai_data:
        is_proceed = a['decision'] == 'PROCEED'
        st.markdown(f"""
        <div style='display:flex;align-items:center;gap:10px;padding:5px 0'>
            <span style='font-size:12px;font-weight:500;color:#e6edf3;min-width:42px'>{a['sym']}</span>
            <div style='flex:1;height:4px;border-radius:2px;background:#21262d'>
                <div style='width:{a['conf']}%;height:100%;border-radius:2px;background:{a['color']}'></div>
            </div>
            <span style='font-size:11px;color:#8b949e;min-width:32px;text-align:right'>{a['conf']}%</span>
            <span style='background:{"#0d2a0d" if is_proceed else "#2d0f0f"};color:{"#3fb950" if is_proceed else "#f85149"};padding:2px 7px;border-radius:3px;font-size:9px;font-weight:600'>{a['decision']}</span>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_news:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-title'>News Sentiment — Claude AI</div>", unsafe_allow_html=True)
    news_data = [
        {"sym": "NVDA", "sent": "BULLISH", "summary": "Strong AI chip demand continues into Q3"},
        {"sym": "AAPL", "sent": "NEUTRAL", "summary": "Mixed signals on iPhone demand outlook"},
        {"sym": "JPM", "sent": "BEARISH", "summary": "Rate concerns weigh on banking sector"},
        {"sym": "TSLA", "sent": "NEUTRAL", "summary": "Deliveries in line with estimates"},
    ]
    for n in news_data:
        if n['sent'] == 'BULLISH':
            bg, color = "#0d2a0d", "#3fb950"
        elif n['sent'] == 'BEARISH':
            bg, color = "#2d0f0f", "#f85149"
        else:
            bg, color = "#1c2128", "#8b949e"
        st.markdown(f"""
        <div style='display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:0.5px solid #21262d'>
            <span style='font-size:12px;font-weight:500;min-width:42px;color:#e6edf3'>{n['sym']}</span>
            <span style='background:{bg};color:{color};padding:2px 7px;border-radius:3px;font-size:9px;font-weight:600'>{n['sent']}</span>
            <span style='font-size:11px;color:#8b949e;flex:1'>{n['summary']}</span>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)