import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

# 1. ページ全体の初期設定
st.set_page_config(page_title="米国株ポートフォリオ・ヒートマップ", layout="wide")
st.title("📊 米国株ポートフォリオ・ヒートマップ＆分析")
st.caption("yfinanceのリアルタイムデータと時系列データを活用した投資管理ダッシュボード")

# 2. CSVファイルの読み込み
@st.cache_data
def load_portfolio_csv():
    try:
        return pd.read_csv("portfolio.csv")
    except FileNotFoundError:
        st.error("`portfolio.csv` が見つかりません。同じフォルダにファイルを作成してください。")
        st.stop()

df_portfolio = load_portfolio_csv()
tickers = df_portfolio['Ticker'].tolist()

# 3. yfinanceから現在の株価やセクター情報を取得
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
            'Ticker': ticker,
            'Name': name,
            'Sector': sector,
            'Price': current_price,
            'ChangePct': price_change_pct
        })
    return pd.DataFrame(data_list)

with st.spinner("最新の市場データを取得中..."):
    df_market = fetch_current_stock_data(tickers)

# 保有情報と市場データを合体させ、評価額を計算
df_all = pd.merge(df_portfolio, df_market, on='Ticker')
df_all['MarketValue'] = df_all['Price'] * df_all['Shares']
total_portfolio_value = df_all['MarketValue'].sum()

# ヒートマップ用のラベル
df_all['HeatmapLabel'] = df_all.apply(
    lambda row: f"<b>{row['Ticker']}</b><br>{row['ChangePct']:+.2f}%", axis=1
)

# ==========================================
# サイドバー設定（過去何ヶ月の推移を見るか選択可能に）
# ==========================================
st.sidebar.header("⚙️ グラフ表示設定")
period_options = {
    "過去1ヶ月 (1mo)": "1mo",
    "過去3ヶ月 (3mo)": "3mo",
    "過去半年 (6mo)": "6mo",
    "過去1年 (1y)": "1y",
    "年初来 (ytd)": "ytd"
}
selected_period_label = st.sidebar.selectbox("時系列グラフの表示期間", list(period_options.keys()), index=2) # 初期値は過去半年
selected_period_code = period_options[selected_period_label]

# ==========================================
# 画面構成：上部 サマリー
# ==========================================
st.metric(label="ポートフォリオ総資産額", value=f"${total_portfolio_value:,.2f}")
st.write("---")

# ==========================================
# 画面構成：メインエリア（四角のヒートマップ）
# ==========================================
st.subheader("🟩 ポートフォリオ・ヒートマップ（前日比）")
st.caption("四角の大きさ＝保有割合（評価額）、色＝前日比（赤：下落、緑：上昇）")

# 視認性の高いTradingView風のカラー（赤〜ダークグレー〜緑）
custom_colors = ['#f23645', '#434651', '#089981']

fig_tree = px.treemap(
    df_all,
    path=[px.Constant("全資産"), 'Sector', 'Ticker'], 
    values='MarketValue',    
    color='ChangePct',       
    color_continuous_scale=custom_colors,
    color_continuous_midpoint=0,      
    custom_data=['Name', 'ChangePct', 'MarketValue', 'HeatmapLabel']
)

# 割合を見やすくするために、マスとマスの間に明確な境界線（黒線）を引く
fig_tree.update_traces(
    text=df_all['HeatmapLabel'], 
    textposition='middle center',
    textfont=dict(size=18, color="white"), 
    marker=dict(line=dict(color='#000000', width=2)), 
    hovertemplate="<b>%{customdata[0]}</b><br>前日比: %{customdata[1]:+.2f}%<br>評価額: $%{customdata[2]:,.2f}"
)

fig_tree.update_layout(
    margin=dict(t=10, l=10, r=10, b=10),
    coloraxis_colorbar=dict(title="騰落率 (%)")
)

st.plotly_chart(fig_tree, use_container_width=True, height=600)

# ==========================================
# 画面構成：下部（円グラフ ＆ 時系列推移）
# ==========================================
st.write("---")
col1, col2 = st.columns(2)

with col1:
    st.subheader("🍕 資産配分（円グラフ）")
    fig_pie = px.pie(
        df_all, values='MarketValue', names='Ticker', hole=0.4,
        custom_data=['Sector', 'MarketValue']
    )
    fig_pie.update_traces(
        hovertemplate="<b>%{label}</b><br>セクター: %{customdata[0]}<br>評価額: $%{customdata[1]:,.2f}",
        marker=dict(line=dict(color='#000000', width=1))
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader(f"📈 累積リターン推移（{selected_period_label}）")
    st.caption("選択した期間の開始日を基準(0%)とした、資産および個別銘柄の投資成果")
    
    # 選択された期間(period)を引数に渡すように修正
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

    with st.spinner("選択された期間の時系列データを解析中..."):
        df_history = fetch_historical_prices(tickers, selected_period_code)

    if not df_history.empty:
        df_filled = df_history.ffill().bfill()
        
        # 1. 各銘柄の累積リターンを計算
        df_returns = (df_filled / df_filled.iloc[0] - 1) * 100
        
        # 2. 「ポートフォリオ全体」の累積リターンを計算
        df_portfolio_value = pd.DataFrame(index=df_filled.index)
        for t in tickers:
            shares = df_portfolio.loc[df_portfolio['Ticker'] == t, 'Shares'].values[0]
            df_portfolio_value[t] = df_filled[t] * shares
            
        df_portfolio_value['Total'] = df_portfolio_value.sum(axis=1)
        # 指定期間の初日を基準(0%)とした全体の累積推移を計算
        df_returns['🌟 ポートフォリオ全体'] = (df_portfolio_value['Total'] / df_portfolio_value['Total'].iloc[0] - 1) * 100
        
        # グラフ用にデータを整形
        plot_columns = tickers + ['🌟 ポートフォリオ全体']
        df_melted = df_returns.reset_index().melt(id_vars=['Date'], value_vars=plot_columns, var_name='Ticker', value_name='ReturnPct')
        
        fig_line = px.line(
            df_melted, x='Date', y='ReturnPct', color='Ticker',
            labels={'ReturnPct': '累積リターン (%)', 'Date': '日付'}
        )
        
        # ポートフォリオ全体の線を太くして目立たせる
        for trace in fig_line.data:
            if trace.name == '🌟 ポートフォリオ全体':
                trace.line.width = 4
            else:
                trace.line.width = 1.5

        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("データが取得できませんでした。")