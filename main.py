import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import datetime # 日付操作のために追加

# 1. ページ全体の初期設定
st.set_page_config(page_title="米国株ポートフォリオ総合分析", layout="wide")
st.title("📊 米国株ポートフォリオ 総合分析ダッシュボード")
st.caption("現金管理・ベンチマーク比較・期間連動型ヒートマップを網羅した完全版")

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

has_cash_usd = 'CASH_USD' in df_portfolio['Ticker'].values
has_cash_jpy = 'CASH_JPY' in df_portfolio['Ticker'].values
stock_tickers = df_portfolio[~df_portfolio['Ticker'].isin(['CASH_USD', 'CASH_JPY'])]['Ticker'].tolist()

cash_usd_amount = df_portfolio.loc[df_portfolio['Ticker'] == 'CASH_USD', 'Shares'].values[0] if has_cash_usd else 0
cash_jpy_amount = df_portfolio.loc[df_portfolio['Ticker'] == 'CASH_JPY', 'Shares'].values[0] if has_cash_jpy else 0

# 3. データ取得関数（現在値・為替）
@st.cache_data(ttl=3600)
def fetch_current_stock_data(ticker_list):
    data_list = []
    for ticker in ticker_list:
        t = yf.Ticker(ticker)
        info = t.info
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0
        name = info.get('shortName', ticker)
        sector = info.get('sector', 'ETF / その他') 
        data_list.append({'Ticker': ticker, 'Name': name, 'Sector': sector, 'Price': current_price})
    return pd.DataFrame(data_list)

@st.cache_data(ttl=3600)
def fetch_exchange_rate():
    try:
        info = yf.Ticker("USDJPY=X").info
        return info.get('regularMarketPrice') or info.get('previousClose') or 150.0
    except:
        return 150.0

# 時系列データの取得関数（指定期間・カスタム日付・分足対応に進化）
@st.cache_data(ttl=3600)
def fetch_historical_prices(ticker_list, period=None, start_date=None, end_date=None):
    # カスタム日付指定の場合
    if start_date and end_date:
        # yfinanceの仕様で終了日が含まれないため+1日する
        end_plus_one = end_date + datetime.timedelta(days=1)
        df_raw = yf.download(ticker_list, start=start_date, end=end_plus_one)
    else:
        # プリセット期間の場合（超短期は分足にしてグラフを滑らかにする）
        if period == "1d":
            df_raw = yf.download(ticker_list, period="1d", interval="5m") # 1日は5分足
        elif period == "3d":
            df_raw = yf.download(ticker_list, period="5d", interval="15m") # 3日は15分足（土日を考慮して5日分取得）
            # 最新の3日分（目安）のデータに絞る
            if not df_raw.empty:
                df_raw = df_raw.tail(72) # 15分足 × 約24本/日 × 3日
        elif period == "5d":
            df_raw = yf.download(ticker_list, period="5d", interval="15m") # 1週間は15分足
        else:
            df_raw = yf.download(ticker_list, period=period) # それ以上は通常の日足

    try:
        df_hist = df_raw['Adj Close']
    except KeyError:
        try:
            df_hist = df_raw['Close']
        except KeyError:
            return pd.DataFrame()
            
    if isinstance(df_hist, pd.Series):
        df_hist = df_hist.to_frame(name=ticker_list[0])
    return df_hist

# ==========================================
# サイドバー設定（カレンダー指定モードを追加）
# ==========================================
st.sidebar.header("⚙️ グラフ表示設定")

period_mode = st.sidebar.radio("期間の指定方法", ["プリセットから選ぶ", "カレンダーで指定する"])

selected_period_code = None
start_date = None
end_date = None

if period_mode == "プリセットから選ぶ":
    period_options = {
        "過去1日 (1d)": "1d",
        "過去3日 (3d)": "3d",
        "過去1週間 (1wk)": "5d", # 営業日ベースで5日
        "過去1ヶ月 (1mo)": "1mo",
        "過去3ヶ月 (3mo)": "3mo",
        "過去半年 (6mo)": "6mo",
        "過去1年 (1y)": "1y",
        "年初来 (ytd)": "ytd"
    }
    selected_period_label = st.sidebar.selectbox("分析対象の期間", list(period_options.keys()), index=4)
    selected_period_code = period_options[selected_period_label]
else:
    selected_period_label = "カスタム指定期間"
    # デフォルトは過去1ヶ月
    default_start = datetime.date.today() - datetime.timedelta(days=30)
    default_end = datetime.date.today()
    
    date_range = st.sidebar.date_input(
        "開始日と終了日を選択してください",
        value=(default_start, default_end),
        max_value=datetime.date.today()
    )
    
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        st.sidebar.warning("👈 開始日と終了日の両方をクリックして選択してください。")
        st.stop() # 2つの日付が選ばれるまで処理を止める

st.sidebar.write("---")
st.sidebar.subheader("👁️ 表示するグラフの線")
display_portfolio_total = st.sidebar.checkbox("🌟 ポートフォリオ全体", value=True)

include_cash_in_trend = False
if (has_cash_usd or has_cash_jpy) and display_portfolio_total:
    include_cash_in_trend = st.sidebar.checkbox("💵 現金(ドル・円)を推移計算に含める", value=True)

selected_tickers = st.sidebar.multiselect("保有銘柄の表示", options=stock_tickers, default=[])
selected_benchmarks = st.sidebar.multiselect("比較する指数・ベンチマーク", options=list(BENCHMARKS.keys()), default=["S&P 500"])

# データの取得開始
with st.spinner("市場データと時系列データを取得中..."):
    df_market_stocks = fetch_current_stock_data(stock_tickers)
    current_fx_rate = fetch_exchange_rate()
    
    benchmark_tickers = [BENCHMARKS[b] for b in selected_benchmarks]
    all_tickers_to_fetch = stock_tickers + benchmark_tickers
    
    # 選択されたモード（プリセット or カスタム）に従ってデータを取得
    df_history = fetch_historical_prices(all_tickers_to_fetch, selected_period_code, start_date, end_date) if all_tickers_to_fetch else pd.DataFrame()

# 現金データの生成と統合
cash_rows = []
if has_cash_usd:
    cash_rows.append({'Ticker': 'CASH_USD', 'Name': '米ドル現金', 'Sector': '現金 (Cash)', 'Price': 1.0})
if has_cash_jpy:
    cash_rows.append({'Ticker': 'CASH_JPY', 'Name': '日本円現金', 'Sector': '現金 (Cash)', 'Price': 1.0 / current_fx_rate})

df_market_all = pd.concat([df_market_stocks, pd.DataFrame(cash_rows)], ignore_index=True) if cash_rows else df_market_stocks

# 評価額の計算
df_all = pd.merge(df_portfolio, df_market_all, on='Ticker')
df_all['MarketValue'] = df_all['Price'] * df_all['Shares']
total_portfolio_value = df_all['MarketValue'].sum()
total_cash_usd_value = cash_usd_amount + (cash_jpy_amount / current_fx_rate)

# ヒートマップ用データの生成（期間騰落率の計算）
df_stocks_only = df_all[~df_all['Ticker'].isin(['CASH_USD', 'CASH_JPY'])].copy()

if not df_history.empty and not df_stocks_only.empty:
    df_filled = df_history.ffill().bfill()
    period_changes = {}
    for t in stock_tickers:
        if t in df_filled.columns:
            initial_p = df_filled[t].iloc[0]
            final_p = df_filled[t].iloc[-1]
            change_pct = ((final_p - initial_p) / initial_p) * 100 if initial_p != 0 else 0
            period_changes[t] = change_pct
        else:
            period_changes[t] = 0.0
    df_stocks_only['PeriodChangePct'] = df_stocks_only['Ticker'].map(period_changes)
else:
    df_stocks_only['PeriodChangePct'] = 0.0

df_stocks_only['HeatmapLabel'] = df_stocks_only.apply(
    lambda row: f"<b>{row['Ticker']}</b><br>{row['PeriodChangePct']:+.2f}%", axis=1
)

# ==========================================
# 画面構成：上部 サマリー
# ==========================================
col_sum1, col_sum2, col_sum3 = st.columns(3)
col_sum1.metric("総資産額（ドル換算）", f"${total_portfolio_value:,.2f}")
col_sum2.metric("うち 保有現金合計", f"${total_cash_usd_value:,.2f}")
col_sum3.metric("為替レート (USD/JPY)", f"¥{current_fx_rate:,.2f}")
st.write("---")

# ==========================================
# 画面構成：中部 ヒートマップ
# ==========================================
st.subheader(f"🟩 米国株ポートフォリオ・ヒートマップ（{selected_period_label}の総変動幅）")

if not df_stocks_only.empty:
    stepped_colorscale = [
        [0.0, '#f23645'], [0.2, '#f23645'],  # 濃い赤 (-5%以下)
        [0.2, "#f76c6e"], [0.4, "#f76c6e"],  # 薄い赤 (-5%〜-2%)
        [0.4, "#A5A7AC"], [0.6, "#A5A7AC"],  # ダークグレー (-2%〜+2%)
        [0.6, "#19d839"], [0.8, "#19d839"],  # 薄い水色 (+2%〜+5%)
        [0.8, "#1e7e0b"], [1.0, "#1e7e0b"]   # 濃い水色 (+5%以上)
    ]

    fig_tree = px.treemap(
        df_stocks_only, path=[px.Constant("保有株式"), 'Sector', 'Ticker'], 
        values='MarketValue', color='PeriodChangePct',
        color_continuous_scale=stepped_colorscale, color_continuous_midpoint=0, 
        custom_data=['Name', 'PeriodChangePct', 'MarketValue']
    )
    fig_tree.update_traces(
        text=df_stocks_only['HeatmapLabel'], textposition='middle center',
        textfont=dict(size=18, color="white"), marker=dict(line=dict(color='#000000', width=2)),
        hovertemplate="<b>%{label}</b><br>名称: %{customdata[0]}<br>期間騰落率: %{customdata[1]:+.2f}%<br>評価額: $%{customdata[2]:,.2f}"
    )
    fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10), coloraxis_colorbar=dict(title="期間騰落率 (%)"))
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
    fig_pie = px.pie(df_all, values='MarketValue', names='Ticker', hole=0.4, custom_data=['Sector', 'MarketValue'])
    fig_pie.update_traces(
        hovertemplate="<b>%{label}</b><br>セクター: %{customdata[0]}<br>評価額: $%{customdata[1]:,.2f}",
        marker=dict(line=dict(color='#000000', width=1))
    )
    fig_pie.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5), margin=dict(t=10, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader(f"📈 累積リターン比較推移（{selected_period_label}）")
    
    if not df_history.empty:
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
            fig_line = px.line(df_melted, x='Date', y='ReturnPct', color='Ticker', labels={'ReturnPct': '累積リターン (%)', 'Date': '日時'})
            
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
    else:
        st.info("選択された期間のデータが取得できませんでした。休場日のみを指定している可能性があります。")
