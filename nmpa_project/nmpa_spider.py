import time
import pandas as pd
from playwright.sync_api import sync_playwright
import os

def run():
    # 确保输出文件存在，如果不存在先创建一个带表头的
    output_file = "guangdong_cosmetics.csv"
    if not os.path.exists(output_file):
        df = pd.DataFrame(columns=["产品名称", "企业名称", "注册证号", "批准日期", "产品执行标准全文"])
        df.to_csv(output_file, index=False, encoding='utf-8-sig')

    # 启动 Playwright
    with sync_playwright() as p:
        # 启动浏览器，headless=False 表示你可以看到浏览器操作过程
        print("正在启动浏览器...")
        browser = p.chromium.launch(headless=False, slow_mo=1000)

        # 创建一个上下文，设置较大的视口，模拟真实用户
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={"width": 1400, "height": 900}
        )
        page = context.new_page()

        # 目标网址
        url = "https://www.nmpa.gov.cn/datasearch/home-index.html?itemId=ff8080818046502f0180f934f6873f78#category=hzp"
        print(f"正在打开网页: {url}")
        try:
            page.goto(url, timeout=60000, wait_until="networkidle")
        except:
            print("网页加载超时，尝试继续操作...")

        # 等待页面加载完成
        print("等待网页初始加载 (5秒)...")
        page.wait_for_timeout(5000)

        # 点击“广东省”
        print("正在尝试筛选 '广东省'...")
        current_page = page

        try:
            with context.expect_page(timeout=15000) as new_page_info:
                # 尝试点击包含“广东”的文本
                page.click("text=广东", timeout=5000)
                print("已点击 '广东'")

            new_popup = new_page_info.value
            new_popup.wait_for_load_state()
            print("检测到新窗口弹出，正在切换到新窗口...")
            current_page = new_popup
            current_page.wait_for_timeout(3000)

        except Exception:
            print("未检测到新窗口弹出，请在浏览器中手动点击'广东省' (等待10秒)...")
            page.wait_for_timeout(10000)
            if len(context.pages) > 1:
                print("检测到多个窗口，自动切换到最新的窗口...")
                current_page = context.pages[-1]
                current_page.wait_for_load_state()
            else:
                current_page = page

        # 循环翻页
        page_num = 1
        page = current_page

        while True:
            print(f"\n--- 正在处理第 {page_num} 页 ---")
            page.wait_for_timeout(3000) # 等待列表渲染

            # 获取所有行
            # 策略：ElementUI 表格通常是 tr.el-table__row
            rows = page.locator("tr.el-table__row").all()
            if len(rows) == 0:
                rows = page.locator("tr").all() # 降级策略

            print(f"当前页面检测到 {len(rows)} 行数据")

            if len(rows) > 0:
                # 打印第一行HTML用于调试
                print(f"DEBUG: 第一行HTML片段: {rows[0].inner_html()[:100]}...")

            processed_count = 0
            for i, row in enumerate(rows):
                try:
                    row_text = row.inner_text()
                    if "产品名称" in row_text and "注册人" in row_text:
                        continue # 跳过表头

                    # 查找“详情”按钮
                    # 根据图片，最后一列是详情按钮
                    detail_btn = row.locator("button:has-text('详情'), a:has-text('详情'), span:has-text('详情')").first

                    if detail_btn.count() == 0:
                        print(f"第 {i+1} 行未找到详情按钮，跳过。")
                        continue

                    print(f"正在点击第 {i+1} 行详情...")

                    # 详情页通常是弹窗还是新页面？
                    # 假设是新页面，因为之前逻辑是这样。如果不是，下面 expect_page 会超时
                    # 许多 ElementUI 详情可能是弹窗(Dialog)，也可能是跳转
                    # 观察之前的 trace，NMPA 详情页通常是跳转/新标签
                    try:
                        with context.expect_page(timeout=5000) as detail_page_info:
                            detail_btn.click(force=True)
                        new_page = detail_page_info.value
                    except:
                        # 如果没有新页面弹出，可能是当前页面的 Dialog
                        print("未检测到详情页新窗口，可能是当前页弹窗（暂不支持弹窗抓取，请反馈）...")
                        continue

                    new_page.wait_for_load_state()
                    new_page.wait_for_timeout(1000)

                    # --- 详情页数据提取 ---
                    # 检查状态
                    body_text = new_page.inner_text("body")
                    if "当前批件" not in body_text:
                         print("状态不是当前批件，跳过")
                         new_page.close()
                         continue

                    # 提取函数
                    def get_value(label):
                        # 尝试 td + td
                        t = new_page.locator(f"td:has-text('{label}') + td").first
                        if t.count() > 0: return t.inner_text().strip()
                        # 尝试 div 兄弟
                        t = new_page.locator(f"//div[contains(text(), '{label}')]/following-sibling::div[1]").first
                        if t.count() > 0: return t.inner_text().strip()
                        return ""

                    product_name = get_value("产品名称中文")
                    enterprise_name = get_value("注册人中文")
                    if not enterprise_name: enterprise_name = get_value("备案人中文")
                    reg_no = get_value("注册证号")
                    if not reg_no: reg_no = get_value("备案编号")
                    approve_date = get_value("批准日期")

                    # 提取执行标准 (再次弹窗)
                    formula = "无"
                    try:
                        # 寻找包含“产品执行的标准”的行中的链接
                        # 或者查找页面上任何叫“查看”的链接，且位于标准附近
                        view_btn = new_page.locator("td:has-text('产品执行的标准')").locator("xpath=..").locator("text=查看").first
                        if view_btn.count() == 0:
                             # 尝试更宽泛的
                             view_btn = new_page.locator("text=查看").first

                        if view_btn.count() > 0:
                            view_btn.click()
                            new_page.wait_for_timeout(1500)
                            # 抓取弹窗内容
                            dialog = new_page.locator(".el-dialog__body").first
                            if dialog.count() > 0:
                                formula = dialog.inner_text().replace("\n", " ")
                            else:
                                formula = "弹窗未定位到"
                        else:
                            formula = "无查看按钮"
                    except Exception as e:
                        formula = f"标准提取失败: {e}"

                    print(f"成功抓取: {product_name}")

                    new_row = {
                        "产品名称": product_name,
                        "企业名称": enterprise_name,
                        "注册证号": reg_no,
                        "批准日期": approve_date,
                        "产品执行标准全文": formula
                    }
                    df = pd.DataFrame([new_row])
                    df.to_csv(output_file, mode='a', header=False, index=False, encoding='utf-8-sig')

                    new_page.close()
                    processed_count += 1

                except Exception as e:
                    print(f"行处理异常: {e}")
                    try: new_page.close()
                    except: pass

            if processed_count == 0:
                print("本页未成功抓取数据。")

            # 翻页
            print("尝试翻页...")
            try:
                # 定位器：
                # 1. class 为 btn-next 的 button (ElementUI 标准)
                # 2. 包含 > 的 button 或 li
                next_btn = page.locator("button.btn-next").first
                if next_btn.count() == 0:
                    next_btn = page.locator("li.next").first # 有时候点击 li 也可以
                if next_btn.count() == 0:
                    next_btn = page.locator("button:has-text('>')").first

                if next_btn.count() > 0 and not next_btn.is_disabled():
                    next_btn.click()
                    page_num += 1
                else:
                    print("无法找到下一页或已到最后一页。")
                    break
            except Exception as e:
                print(f"翻页出错: {e}")
                break

        print("任务结束。")
        browser.close()

if __name__ == "__main__":
    run()
