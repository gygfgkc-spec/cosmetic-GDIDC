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
        # 定义一个变量来存储当前正在操作的页面
        # 默认是当前页面
        current_page = page

        try:
            # 策略：如果点击广东会弹出新页面，我们需要捕获这个新页面
            # 先尝试监听新页面事件
            with context.expect_page(timeout=10000) as new_page_info:
                # 尝试点击包含“广东”的文本
                page.click("text=广东", timeout=5000)
                print("已点击 '广东'")

            # 如果成功捕获到新页面
            new_popup = new_page_info.value
            new_popup.wait_for_load_state()
            print("检测到新窗口弹出，正在切换到新窗口...")
            current_page = new_popup
            # 等待新窗口内容加载
            current_page.wait_for_timeout(3000)

        except Exception:
            # 如果没有弹出新页面（超时），或者点击失败
            print("未检测到新窗口弹出，继续在当前窗口操作...")
            # 也有可能是自动点击失败了，再次提示用户手动操作
            # 但这里我们假设如果自动点击失败，用户会手动点
            # 如果用户手动点了导致弹窗，Playwright 可能捕获不到（因为它在等代码里的操作）
            # 所以这里做一个更通用的处理：
            # 如果上面自动点击没反应，给用户时间手动点，并检查是否有新页面生成

            print("如果自动点击失败，请在浏览器中手动点击'广东省'。")
            page.wait_for_timeout(5000)

            # 检查是否有新的页面（Context 里的 pages 数量）
            if len(context.pages) > 1:
                print("检测到多个窗口，自动切换到最新的窗口...")
                current_page = context.pages[-1]
                current_page.wait_for_load_state()
            else:
                # 仍然是当前页
                current_page = page

        # 循环翻页
        page_num = 1
        # 后面的操作全部基于 current_page
        page = current_page
        while True:
            print(f"正在处理第 {page_num} 页...")

            # 等待列表加载
            page.wait_for_timeout(2000)

            # 获取所有详情页链接
            # 根据经验，NMPA 列表页的每一项通常是一个链接或者包含一个链接
            # 我们查找所有有 href 属性且看起来是结果的链接
            # 这里使用一个比较宽泛的策略：获取所有 target="_blank" 的链接，或者位于主要内容区的链接

            # 由于无法查看源码，我们采用一种交互式策略：
            # 找到所有的列表行，然后分别处理

            # 假设列表选择器
            # 我们尝试获取页面上所有的 "a" 标签，并过滤出可能是详情页的
            # 通常详情页链接包含 "itemId" 或 "id"
            # 或者我们通过视觉位置判断（在页面中间的）

            # 为了代码的健壮性，这里假设每一行是一个 tr 或者 li
            # 并且包含一个可以点击的标题

            # 获取当前页所有结果的句柄（Snapshot）
            # 假设每页 15 条，我们尝试找到这 15 个入口
            # 许多政府网站使用 table 布局
            rows = page.locator("table tr").all()

            # 如果没找到 table，尝试找 list
            if len(rows) < 5:
                rows = page.locator(".list-item, .el-card").all()

            print(f"当前页面检测到 {len(rows)} 行数据 (包括表头)")

            processed_count = 0
            for row in rows:
                try:
                    # 排除表头：检查是否包含"产品名称"等字样
                    if "产品名称" in row.inner_text() or "注册人" in row.inner_text():
                        continue

                    # 找到该行中的链接
                    # 点击该行的第一个链接，或者是“查看”按钮
                    link = row.locator("a").first
                    if link.count() == 0:
                        continue # 这一行没有链接

                    # 模拟点击，打开新页面
                    with context.expect_page() as new_page_info:
                        link.click()

                    new_page = new_page_info.value
                    new_page.wait_for_load_state()
                    new_page.wait_for_timeout(1000) # 稍等渲染

                    # --- 详情页处理 ---
                    # 1. 检查状态 "当前批件"
                    # 使用 text 包含匹配，定位到"状态"这一行
                    # 假设是 key-value 结构
                    page_text = new_page.inner_text("body")

                    # 快速检查：如果整个页面里没有“当前批件”，可能就不是（或者状态是别的）
                    # 但为了严谨，我们定位字段

                    # 定义提取函数
                    def get_value(label):
                        # 尝试多种定位方式
                        # 1. td(label) + td
                        # 2. div(label) + div
                        try:
                            return new_page.locator(f"td:has-text('{label}') + td").inner_text().strip()
                        except:
                            try:
                                return new_page.locator(f"xpath=//div[contains(text(), '{label}')]/following-sibling::div[1]").inner_text().strip()
                            except:
                                return ""

                    status = get_value("状态")
                    if "当前批件" not in status and "当前批件" not in page_text:
                        # 如果定位不到但页面文本里有，也算过。如果都没有，就跳过。
                        if "当前批件" not in page_text:
                            print(f"跳过：状态不是当前批件 ({status})")
                            new_page.close()
                            continue

                    # 2. 提取基本信息 (基于用户提供的图片)
                    product_name = get_value("产品名称中文")
                    enterprise_name = get_value("注册人中文")
                    if not enterprise_name:
                         enterprise_name = get_value("备案人中文") # 兼容旧版或不同类目

                    reg_no = get_value("注册证号")
                    if not reg_no:
                        reg_no = get_value("备案编号")

                    approve_date = get_value("批准日期")

                    # 3. 提取执行标准 (弹窗)
                    formula = "未提取"
                    purpose = "未提取"

                    # 点击“查看”
                    # 图片显示“产品执行的标准”后面有个“查看”链接
                    # 定位：找到包含“产品执行的标准”的单元格，然后点击里面的“查看”或者旁边的“查看”
                    try:
                        # 定位包含文本的 td，然后在里面找 a
                        target_td = new_page.locator("td:has-text('产品执行的标准')")
                        if target_td.count() > 0:
                            # 假设查看链接在同一个 td 里，或者下一个 td
                            view_btn = target_td.locator("a").first
                            if view_btn.count() == 0:
                                view_btn = new_page.locator("td:has-text('产品执行的标准') + td a").first

                            if view_btn.count() > 0:
                                view_btn.click()
                                print("已点击查看标准，等待弹窗...")
                                new_page.wait_for_timeout(2000)

                                # 获取弹窗内容
                                # 假设弹窗是 el-dialog
                                dialog = new_page.locator(".el-dialog__body, .modal-body, .dialog-content").first
                                if dialog.count() > 0:
                                    dialog_text = dialog.inner_text()
                                    # 简单清理一下换行，保存全内容
                                    formula = dialog_text.replace("\n", " ")
                                else:
                                    # 如果找不到弹窗容器，就抓取页面上最新可见的文本
                                    formula = "弹窗打开但无法定位内容"
                            else:
                                formula = "无查看按钮"
                        else:
                            formula = "无标准字段"

                    except Exception as e:
                        formula = f"提取出错: {e}"

                    # 打印一下
                    print(f"抓取: {product_name} | {reg_no}")

                    # 写入 CSV
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
                    print(f"处理行出错: {e}")
                    try:
                        new_page.close()
                    except:
                        pass

            if processed_count == 0:
                print("警告：本页没有成功抓取到任何数据。可能需要检查选择器。")

            # 翻页逻辑
            print("尝试翻下一页...")
            try:
                # 查找“下一页”按钮
                # 通常是 class="btn-next" 或者 text=">"
                # 或者是 text="下一页"
                next_btn = page.locator("button.btn-next, a:has-text('下一页'), a:has-text('>')").last

                # 检查是否被禁用 (disabled)
                if next_btn.is_disabled():
                    print("已到达最后一页。")
                    break

                next_btn.click()
                page_num += 1
                page.wait_for_timeout(3000)
            except:
                print("无法找到下一页按钮，停止抓取。")
                break

        print("所有任务完成。")
        browser.close()

if __name__ == "__main__":
    run()
