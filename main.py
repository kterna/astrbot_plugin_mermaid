from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.core.star.register import register_llm_tool as llm_tool
import mermaid as md
from mermaid.graph import Graph
import os
import astrbot.api.message_components as Comp
import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
import uuid  # 添加uuid模块用于生成唯一文件名

@register("mermaid", "kterna", "使用Mermaid语法生成各种图表（思维导图、流程图、时序图等）", "1.0.0", "https://github.com/kterna/astrbot_plugin_mermaid")
class MermaidPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 在插件目录下创建temp文件夹
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_dir = os.path.join(plugin_dir, "temp")
        # 确保temp目录存在
        os.makedirs(self.temp_dir, exist_ok=True)
        # 创建线程池
        self.executor = ThreadPoolExecutor(max_workers=3)
    
    @filter.command("mermaid")
    async def mermaid_command(self, event: AstrMessageEvent):
        '''生成Mermaid图表，使用方法: /mermaid 提示词'''
        # 获取提示词
        prompt = event.message_str.replace("/mermaid", "", 1).strip()
        if not prompt:
            yield event.plain_result("请提供提示词以生成图表，例如：/mermaid 创建一个展示项目开发流程的流程图")
            return
        
        # 向用户发送处理中的消息
        yield event.plain_result("🔄 正在为您生成图表，请稍候...")
        
        # 使用LLM生成图表
        system_prompt = "你是一个擅长制作Mermaid图表的助手，会使用Mermaid语法创建简洁而有条理的图表(flowchart、sequenceDiagram、stateDiagram、erDiagram、journey、pie、mindmap、gantt)。"
        user_prompt = f"请为我创建一个关于'{prompt}'的图表，直接提供Mermaid代码块，以```mermaid开头，以```结尾。如有需要，可以在代码前后添加解释说明。"
        
        # 调用LLM
        llm_response = await self.context.get_using_provider().text_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )
        
        # 提取LLM返回的文本内容
        text = getattr(llm_response, "completion_text", "")
        if not text:
            yield event.plain_result("❌ 生成图表失败：无法获取LLM响应内容")
            return

        # 处理文本和代码块
        result_chain = await self.process_text_with_mermaid(text)
        if not result_chain:
            yield event.plain_result("❌ 未能在LLM响应中找到有效的Mermaid代码")
            return
            
        yield event.chain_result(result_chain)
    
    @llm_tool(name="generate_mermaid")
    async def generate_mermaid(self, event: AstrMessageEvent, mermaid_code: str) -> MessageEventResult:
        '''使用Mermaid语法生成图表。支持flowchart、sequenceDiagram、stateDiagram、erDiagram、journey、pie、mindmap、gantt。
        请根据用户需求选择合适的图表类型，并使用Mermaid语法生成图表。

        Args:
            mermaid_code(string): Mermaid语法代码
        '''
        if not isinstance(mermaid_code, str) or not mermaid_code:
            yield event.plain_result("❌ 无效的Mermaid代码")
            return
            
        # 处理文本和代码块
        result_chain = await self.process_text_with_mermaid(mermaid_code)
        if not result_chain:
            # 尝试直接作为Mermaid代码处理
            resp = await self.mermaid2image(mermaid_code)
            yield event.chain_result(resp)
        else:
            yield event.chain_result(result_chain)
    
    async def process_text_with_mermaid(self, text: str) -> list:
        '''处理文本，提取并转换Mermaid代码块'''
        import re
        
        result_chain = []
        # 分割文本以找到代码块
        # 匹配```mermaid和```之间的内容，或者```和```之间的内容
        mermaid_pattern = r'```mermaid\s*([\s\S]*?)\s*```'
        code_pattern = r'```\s*([\s\S]*?)\s*```'
        
        last_end = 0
        
        # 首先尝试匹配```mermaid代码块
        for match in re.finditer(mermaid_pattern, text):
            # 添加代码块前的文本
            if match.start() > last_end:
                pre_text = text[last_end:match.start()].strip()
                if pre_text:
                    result_chain.append(Comp.Plain(text=pre_text))
            
            # 提取并转换Mermaid代码
            mermaid_code = match.group(1).strip()
            if mermaid_code:
                # 生成图表
                mermaid_result = await self.mermaid2image(mermaid_code)
                result_chain.extend(mermaid_result)
            
            last_end = match.end()
        
        # 如果没有找到```mermaid代码块，尝试匹配普通代码块，并检查它是否可能是Mermaid代码
        if last_end == 0:
            for match in re.finditer(code_pattern, text):
                # 添加代码块前的文本
                if match.start() > last_end:
                    pre_text = text[last_end:match.start()].strip()
                    if pre_text:
                        result_chain.append(Comp.Plain(text=pre_text))
                
                # 提取代码
                code = match.group(1).strip()
                # 检查是否可能是Mermaid代码（包含常见的Mermaid关键字）
                mermaid_keywords = ['graph', 'flowchart', 'sequenceDiagram', 'classDiagram', 
                                   'stateDiagram', 'erDiagram', 'journey', 'gantt', 'pie', 'mindmap']
                is_mermaid = any(keyword in code.lower() for keyword in mermaid_keywords)
                
                if is_mermaid:
                    # 生成图表
                    mermaid_result = await self.mermaid2image(code)
                    result_chain.extend(mermaid_result)
                else:
                    # 作为普通代码块保留
                    result_chain.append(Comp.Plain(text=f"```\n{code}\n```"))
                
                last_end = match.end()
        
        # 添加剩余文本
        if last_end < len(text):
            remaining_text = text[last_end:].strip()
            if remaining_text:
                result_chain.append(Comp.Plain(text=remaining_text))
        
        return result_chain
        
    async def mermaid2image(self, mermaid_code: str) -> list:
        '''将Mermaid语法转换为图像。'''
        max_retries = 3
        retry_count = 0
        base_delay = 1  # 基础延迟1秒
        
        # 生成唯一文件名使用UUID而不是hash
        img_id = uuid.uuid4().hex
        img_path = os.path.join(self.temp_dir, f"mermaid_{img_id}.png")
        
        while retry_count <= max_retries:
            try:                
                # 创建图表并渲染
                graph = Graph("Mermaid图表", mermaid_code)
                render = md.Mermaid(graph)
                
                # 异步执行图表生成
                await asyncio.get_event_loop().run_in_executor(
                    self.executor, 
                    functools.partial(render.to_png, img_path)
                )
                
                # 检查文件是否成功生成
                if not os.path.exists(img_path):
                    raise Exception("图像文件生成失败")
                
                # 验证生成的文件是否为有效的PNG图像
                file_size = os.path.getsize(img_path)
                if file_size < 1024:  # 小于1KB，可能是错误文件
                    # 读取文件内容
                    with open(img_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read().lower()
                    
                    # 检查错误类型
                    import re
                    # 如果是网络错误且还有重试次数，则重试
                    if re.search(r'unknown|network|fail|server', content) and retry_count < max_retries:
                        retry_count += 1
                        # 指数退避延迟
                        delay = base_delay * (2 ** (retry_count - 1))
                        await asyncio.sleep(delay)
                        continue
                    
                    # 清理错误文件
                    self._clean_file(img_path)
                    
                    error_message = "生成图表失败"
                    if re.search(r'unknown|network|fail|server', content):
                        error_message = f"❌ 生成图表失败：出现网络或服务器错误 (已重试{retry_count}次)"
                    elif re.search(r'parse|syntax|invalid|expect', content):
                        error_message = "❌ 生成图表失败：Mermaid语法错误，请检查图表代码"
                    else:
                        error_message = f"❌ 生成图表失败：{content[:100]}..."
                    
                    return [Comp.Plain(text=error_message)]
                
                # 获取响应结果
                response = [
                    Comp.Plain(text="✅ 图表生成成功:\n"),
                    Comp.Image(file=img_path)
                ]
                
                # 标记此文件为待清理状态
                self._schedule_file_cleanup(img_path)
                
                return response
                
            except Exception as e:
                # 确保清理可能部分生成的文件
                if os.path.exists(img_path):
                    self._clean_file(img_path)
                    
                error_msg = str(e).lower()
                # 检查是否是网络连接相关错误
                if (any(network_err in error_msg for network_err in ["connection", "timeout", "network", "server"]) 
                    and retry_count < max_retries):
                    retry_count += 1
                    delay = base_delay * (2 ** (retry_count - 1))
                    await asyncio.sleep(delay)
                    continue
                
                return [Comp.Plain(text=f"❌ 生成图表时发生错误: {str(e)}\n请检查Mermaid语法是否正确，或尝试简化图表内容。")]
        
        # 如果重试全部失败
        return [Comp.Plain(text=f"❌ 生成图表失败：服务器连接问题，已尝试重试{max_retries}次")]
    
    def _clean_file(self, file_path):
        """立即清理文件的辅助方法"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            # 记录错误但不抛出异常
            print(f"清理文件 {file_path} 失败: {str(e)}")
    
    def _schedule_file_cleanup(self, file_path, delay_seconds=300):
        """安排延迟清理文件"""
        async def delayed_cleanup():
            try:
                # 等待指定时间以确保文件已被使用
                await asyncio.sleep(delay_seconds)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"已清理临时文件: {os.path.basename(file_path)}")
            except Exception as e:
                print(f"延迟清理文件 {file_path} 失败: {str(e)}")
                
        # 创建异步任务来执行延迟清理
        asyncio.create_task(delayed_cleanup())