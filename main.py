import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

# 1. ページ全体の初期設定
st.set_page_config(page_title="米国株ポートフォリオ総合分析", layout="wide")
st.title("📊 米国株ポートフォリオ 総合分析ダッシュボード")
st.caption("現金管理・ベンチマーク比較・TradingView風ヒートマップを網羅した完全版")

BENCHMARKS = {
    "S&P 500": "^GSPC",
    "NASDAQ 100": "^NDX",
    "日経225": "^N225",
    "TOPIX": "^TOPX"
}

# 2. CSVファイルの読み込み
@st.cache_data
def load_portfolio_csv():
    try:
        df = pd.read_csv("portfolio.csv")
        df['Ticker'] = df['Ticker'].str.strip().str.upper()
        return df
    except FileNotFoundError:
        st.error("`portfolio.csv` が見つかりません。同じフォルダにファイルを作成してください。")
        st.stop()

df_portfolio = load_portfolio_csv()

# 現金と株の分離
has_cash_usd = 'CASH_USD' in df_portfolio['Ticker'].values
has_cash_jpy = 'CASH_JPY' in df_portfolio['Ticker'].values
stock_tickers = df_portfolio[~df_portfolio['Ticker'].isin(['CASH_USD', 'CASH_JPY'])]['Ticker'].tolist()

cash_usd_amount = df_portfolio.loc[df_portfolio['Ticker'] == 'CASH_USD', 'Shares'].values[0] if has_cash_usd else 0
cash_jpy_amount = df_portfolio.loc[df_portfolio['Ticker'] == 'CASH_JPY', 'Shares'].values[0] if has_cash_jpy else 0

# 3. yfinanceからデータ取得
@st.cache_data(ttl=3600)
def fetch_current_stock_data(ticker_list):
    data_list = []
    for ticker in ticker_list:
        t = yf.Ticker(ticker)
        info = t.info
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0
        prev_close = info.get('previousClose') or current_price
        name = info.get('shortName', ticker)
        sector = info.get('sector', 'ETF / その他') 
        price_change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0
        
        data_list.append({
            'Ticker': ticker, 'Name': name, 'Sector': sector, 'Price': current_price, 'ChangePct': price_change_pct
        })
    return pd.DataFrame(data_list)

@st.cache_data(ttl=3600)
def fetch_exchange_rate():
    try:
        info = yf.Ticker("USDJPY=X").info
        return info.get('regularMarketPrice') or info.get('previousClose') or 150.0
    except:
        return 150.0

with st.spinner("最新の市場データと為替レートを取得中..."):
    df_market_stocks = fetch_current_stock_data(stock_tickers)
    current_fx_rate = fetch_exchange_rate()

# ダッシュボード全体用のデータを作成（株＋現金）
cash_rows = []
if has_cash_usd:
    cash_rows.append({'Ticker': 'CASH_USD', 'Name': '米ドル現金', 'Sector': '現金 (Cash)', 'Price': 1.0, 'ChangePct': 0.0})
if has_cash_jpy:
    cash_rows.append({'Ticker': 'CASH_JPY', 'Name': '日本円現金', 'Sector': '現金 (Cash)', 'Price': 1.0 / current_fx_rate, 'ChangePct': 0.0})

df_market_all = pd.concat([df_market_stocks, pd.DataFrame(cash_rows)], ignore_index=True) if cash_rows else df_market_stocks

# 評価額（ドル）の計算
df_all = pd.merge(df_portfolio, df_market_all, on='Ticker')
df_all['MarketValue'] = df_all['Price'] * df_all['Shares']
total_portfolio_value = df_all['MarketValue'].sum()
total_cash_usd_value = cash_usd_amount + (cash_jpy_amount / current_fx_rate)

# 株だけのデータを抽出（ヒートマップ用）
df_stocks_only = df_all[~df_all['Ticker'].isin(['CASH_USD', 'CASH_JPY'])].copy()
df_stocks_only['HeatmapLabel'] = df_stocks_only.apply(
    lambda row: f"<b>{row['Ticker']}</b><br>{row['ChangePct']:+.2f}%", axis=1
)

# ==========================================
# サイドバー設定
# ==========================================
st.sidebar.header("⚙️ グラフ表示設定")
period_options = {"過去1ヶ月": "1mo", "過去3ヶ月": "3mo", "過去半年": "6mo", "過去1年": "1y", "年初来": "ytd"}
selected_period_label = st.sidebar.selectbox("時系列グラフの表示期間", list(period_options.keys()), index=2)
selected_period_code = period_options[selected_period_label]

st.sidebar.write("---")
st.sidebar.subheader("👁️ 表示するグラフの線")
display_portfolio_total = st.sidebar.checkbox("🌟 ポートフォリオ全体", value=True)

include_cash_in_trend = False
if (has_cash_usd or has_cash_jpy) and display_portfolio_total:
    include_cash_in_trend = st.sidebar.checkbox(
        "💵 現金(ドル・円)を全体の推移計算に含める", 
        value=True,
        help="ON: 現金がクッションとなり変動が緩やかになります。OFF: 株だけの純粋な運用成績になります。"
    )

selected_tickers = st.sidebar.multiselect("保有銘柄の表示", options=stock_tickers, default=[])
selected_benchmarks = st.sidebar.multiselect("比較する指数・ベンチマーク", options=list(BENCHMARKS.keys()), default=["S&P 500"])

# ==========================================
# 画面構成：上部 サマリー
# ==========================================
col_sum1, col_sum2, col_sum3 = st.columns(3)
col_sum1.metric("総資産額（ドル換算）", f"${total_portfolio_value:,.2f}")
col_sum2.metric("うち 保有現金合計", f"${total_cash_usd_value:,.2f}")
col_sum3.metric("為替レート (USD/JPY)", f"¥{current_fx_rate:,.2f}")
st.write("---")

# ==========================================
# 画面構成：中部 ヒートマップ（株のみで復活！）
# ==========================================
st.subheader("🟩 米国株ポートフォリオ・ヒートマップ（前日比）")
st.caption("四角の大きさ＝株の中での保有割合、色＝前日比の騰落率（現金は自動的に除外されています）")

if not df_stocks_only.empty:
    custom_colors = ['#f23645', '#434651', '#089981'] # TradingView風カラー
    fig_tree = px.treemap(
        df_stocks_only, path=[px.Constant("保有株式"), 'Sector', 'Ticker'], 
        values='MarketValue', color='ChangePct', color_continuous_scale=custom_colors,
        color_continuous_midpoint=0, custom_data=['Name', 'ChangePct', 'MarketValue']
    )
    fig_tree.update_traces(
        text=df_stocks_only['HeatmapLabel'], textposition='middle center',
        textfont=dict(size=18, color="white"), marker=dict(line=dict(color='#000000', width=2)),
        hovertemplate="<b>%{label}</b><br>名称: %{customdata[0]}<br>前日比: %{customdata[1]:+.2f}%<br>評価額: $%{customdata[2]:,.2f}"
    )
    fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10), coloraxis_colorbar=dict(title="騰落率 (%)"))
    st.plotly_chart(fig_tree, use_container_width=True, height=500)
else:
    st.info("保有している株式がありません。")

# ==========================================
# 画面構成：下部（円グラフ ＆ 時系列推移）
# ==========================================
st.write("---")
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("🍕 資産配分（円グラフ・現金含む）")
    st.caption("総資産に対する「株」と「現金（ドル・円）」の本当の比率")
    fig_pie = px.pie(df_all, values='MarketValue', names='Ticker', hole=0.4, custom_data=['Sector', 'MarketValue'])
    fig_pie.update_traces(
        hovertemplate="<b>%{label}</b><br>セクター: %{customdata[0]}<br>評価額: $%{customdata[1]:,.2f}",
        marker=dict(line=dict(color='#000000', width=1))
    )
    fig_pie.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5), margin=dict(t=10, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader(f"📈 累積リターン比較推移（{selected_period_label}）")
    
    @st.cache_data(ttl=3600)
    def fetch_historical_prices(ticker_list, period):
        df_raw = yf.download(ticker_list, period=period)
        try:
            df_hist = df_raw['Adj Close']
        except KeyError:
            df_hist = df_raw['Close']
        if isinstance(df_hist, pd.Series):
            df_hist = df_hist.to_frame(name=ticker_list[0])
        return df_hist

    all_tickers_to_fetch = stock_tickers + [BENCHMARKS[b] for b in selected_benchmarks]

    with st.spinner("時系列データを解析中..."):
        df_history = fetch_historical_prices(all_tickers_to_fetch, selected_period_code) if all_tickers_to_fetch else pd.DataFrame()

    if not df_history.empty:
        df_filled = df_history.ffill().bfill()
        df_filled.rename(columns={v: k for k, v in BENCHMARKS.items()}, inplace=True)
        
        df_returns = (df_filled / df_filled.iloc[0] - 1) * 100
        
        df_portfolio_value = pd.DataFrame(index=df_filled.index)
        for t in stock_tickers:
            if t in df_filled.columns:
                shares = df_portfolio.loc[df_portfolio['Ticker'] == t, 'Shares'].values[0]
                df_portfolio_value[t] = df_filled[t] * shares
                
        daily_stock_total = df_portfolio_value.sum(axis=1)
        
        portfolio_line_name = '🌟 ポートフォリオ全体'
        if display_portfolio_total:
            if include_cash_in_trend:
                daily_total_value = daily_stock_total + total_cash_usd_value
                portfolio_line_name = '🌟 ポートフォリオ全体 (現金込)'
            else:
                daily_total_value = daily_stock_total
                portfolio_line_name = '🌟 ポートフォリオ全体 (株式のみ)'
            
            df_returns[portfolio_line_name] = (daily_total_value / daily_total_value.iloc[0] - 1) * 100
        
        plot_columns = ([portfolio_line_name] if display_portfolio_total else []) + selected_tickers + selected_benchmarks
        
        if plot_columns:
            df_melted = df_returns.reset_index().melt(id_vars=['Date'], value_vars=plot_columns, var_name='Ticker', value_name='ReturnPct')
            fig_line = px.line(df_melted, x='Date', y='ReturnPct', color='Ticker', labels={'ReturnPct': '累積リターン (%)', 'Date': '日付'})
            
            for trace in fig_line.data:
                if '🌟 ポートフォリオ全体' in trace.name:
                    trace.line.width = 4
                elif trace.name in BENCHMARKS.keys():
                    trace.line.width = 3
                    trace.line.dash = 'dot'
                else:
                    trace.line.width = 1.5
    
            fig_line.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5))
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("👈 サイドバーから表示したいグラフの線を選択してください。")