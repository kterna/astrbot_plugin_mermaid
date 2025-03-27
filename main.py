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
        
        # 获取函数调用管理器
        func_tools_mgr = self.context.get_llm_tool_manager()
        
        # 向用户发送处理中的消息
        yield event.plain_result(f"🔄 正在为您生成图表，请稍候...")
        
        # 获取用户ID，用于生成会话ID
        uid = event.unified_msg_origin
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
        
        # 使用LLM生成图表
        system_prompt = "你是一个擅长制作Mermaid图表的助手，会使用Mermaid语法创建简洁而有条理的各种图表（如思维导图、流程图、时序图、甘特图等）。"
        user_prompt = f"请为我创建一个关于'{prompt}'的图表，直接使用generate_mermaid工具，不需要解释，只需要提供Mermaid语法。"
        
        # 调用LLM并使用函数工具
        yield event.request_llm(
            prompt=user_prompt,
            func_tool_manager=func_tools_mgr,
            session_id=curr_cid,
            system_prompt=system_prompt
        )
    
    @llm_tool(name="generate_mermaid")
    async def generate_mermaid(self, event: AstrMessageEvent, mermaid_code: str) -> MessageEventResult:
        '''使用Mermaid语法生成图表。

        Args:
            mermaid_code(string): Mermaid语法代码，支持所有Mermaid图表类型（mindmap、flowchart、sequenceDiagram、gantt等）
        '''
        try:
            # 创建Graph对象
            graph = Graph("Mermaid图表", mermaid_code)
            
            # 渲染图表
            render = md.Mermaid(graph)
            
            # 生成唯一文件名
            img_path = os.path.join(self.temp_dir, f"mermaid_{hash(mermaid_code)}.png")
            
            # 在线程池中异步执行to_png操作，避免堵塞主线程
            await asyncio.get_event_loop().run_in_executor(
                self.executor, 
                functools.partial(render.to_png, img_path)
            )
            
            # 检查文件是否成功生成
            if not os.path.exists(img_path):
                raise Exception("图像文件生成失败")
            
            # 返回图像和消息
            result = [
                Comp.Plain(text="✅ 图表生成成功:\n"),
                Comp.Image(file=img_path)
            ]
            
            return MessageEventResult(result)
            
        except Exception as e:
            return event.plain_result(f"❌ 生成图表时发生错误: {str(e)}\n请检查Mermaid语法是否正确，或尝试简化图表内容。")