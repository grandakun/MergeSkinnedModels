这是一个为你提供的 MergeSkinnedModels.py 脚本编写的 README.md 文档。你可以直接将其保存为 Markdown 文件。

MergeSkinnedModels - Maya 蒙皮模型合并工具
这是一个用于 Autodesk Maya 的 Python 脚本，旨在将多个带有蒙皮（SkinCluster）的网格模型合并为一个单一的网格，同时完美保留并合并所有原有的蒙皮权重。

该版本为无 UI 核心模块版，专为工具链集成（如被 xiaotaTool.py 的面板按钮调用）设计，也完全支持作为独立的工具架（Shelf）按钮使用。

✨ 核心特性
🚀 高效读写：采用底层 OpenMaya API 批量读取和写入顶点权重，速度远超原生的 maya.cmds。

🛡️ 智能过滤与容错：自动识别并跳过未绑定蒙皮的模型；如果选择的模型中有效蒙皮少于 2 个，会自动中止并给出安全提示。

⚠️ 融合变形（BlendShape）检测：自动检测合并对象是否包含 BlendShape，并在 UI 和控制台发出警告（合并会丢失 BS 数据）。

💾 无损权重：自动提取所有参与网格的最大影响点数（maxInfluences），确保写入新模型时权重不被截断。

🧹 场景保洁：自动识别并删除 polyUnite 操作后留下的多余空变换节点（Empty Shells）。

↩️ 一键撤销：整个合并流程被封装在一个完整的 Undo Chunk 中，随时可以使用 Ctrl+Z 安全撤销所有操作。

📦 安装说明
将 MergeSkinnedModels.py 文件复制到你的 Maya 默认脚本目录中。

Windows: C:\Users\<你的用户名>\Documents\maya\scripts\

macOS: ~/Library/Preferences/Autodesk/maya/scripts/

重启 Maya，或者在 Python 脚本编辑器中运行以确保 Maya 能检测到该模块。

🚀 使用方法
方式一：通过脚本编辑器 / 工具架（Shelf）运行
在场景中选中 2个或以上 需要合并的蒙皮模型，然后在 Python 脚本编辑器中执行以下代码。你可以将这段代码直接拖拽到 Maya 的工具架上制成快捷按钮：

Python
from MergeSkinnedModels import merge_selected
merge_selected()
方式二：作为其他 UI/插件 的模块调用
在其他脚本（例如你的 xiaotaTool.py）中，可以直接将其绑定到按钮的 command 事件上：

Python
import maya.cmds as cmds
from MergeSkinnedModels import merge_selected

# 在你的 UI 代码中：
cmds.button(label="合并选中蒙皮", command=lambda *args: merge_selected())
📝 注意事项 (Important Notes)
骨骼重名风险：如果场景中不同层级下有短名（Short Name）相同的骨骼关节，脚本会在控制台（Script Editor）打印警告（⚠ 关节短名冲突...）。为保证权重精确对应，建议在绑定前确保场景骨骼命名唯一。

丢失节点：合并操作本质上是创建了新模型，因此模型上的变形器（如 BlendShape、非线性变形器等）将会丢失。脚本会在完成时给出屏幕提示（In-View Message）和控制台警告以提醒你。

重命名规则：合并后的新模型将继承你所选列表中的第一个有效蒙皮模型的名称，并自动追加 _merged 后缀。
