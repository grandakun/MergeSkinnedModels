# -*- coding: utf-8 -*-
"""
MergeSkinnedModels  ——  合并蒙皮模型（无 UI 模块版）
==================================================
入口：merge_selected()
用法：由 xiaotaTool.py 的 TemplateUI 面板按钮调用。

  from MergeSkinnedModels import merge_selected
  merge_selected()
"""

import maya.cmds as cmds
from maya import OpenMaya as om
from maya import OpenMayaAnim as oma
from collections import Counter
import time


# ─────────────────────────── 内部工具函数 ───────────────────────────

def _get_skin_cluster(mesh):
    """返回 mesh 上的 skinCluster 节点名，找不到返回 None。"""
    history = cmds.listHistory(mesh, pruneDagObjects=True)
    if not history:
        return None
    sc = cmds.ls(history, type='skinCluster')
    return sc[0] if sc else None


def _get_skin_weights(mesh, skin_cluster):
    """用 OpenMaya API 读取 skinCluster 权重。"""
    inf_short = cmds.skinCluster(skin_cluster, q=True, influence=True) or []
    inf_long = cmds.ls(inf_short, long=True)
    inf_count = len(inf_long)
    vtx_count = cmds.polyEvaluate(mesh, vertex=True)

    sel = om.MSelectionList()
    sel.add(skin_cluster)
    mobj = om.MObject()
    sel.getDependNode(0, mobj)
    fn_skin = oma.MFnSkinCluster(mobj)

    sel2 = om.MSelectionList()
    sel2.add(mesh)
    dag = om.MDagPath()
    sel2.getDagPath(0, dag)

    all_ids = om.MIntArray()
    for i in range(vtx_count):
        all_ids.append(i)

    single_comp = om.MFnSingleIndexedComponent()
    vtx_comp = single_comp.create(om.MFn.kMeshVertComponent)
    single_comp.addElements(all_ids)

    weights = om.MDoubleArray()
    su = om.MScriptUtil()
    su.createFromInt(0)
    ptr = su.asUintPtr()
    fn_skin.getWeights(dag, vtx_comp, weights, ptr)

    per_vtx = []
    for v in range(vtx_count):
        d = {}
        base = v * inf_count
        for j in range(inf_count):
            w = weights[base + j]
            if w > 1e-7:
                d[inf_long[j]] = w
        per_vtx.append(d)

    return {'influences': inf_long, 'weights': per_vtx}


def _set_skin_weights(mesh, skin_cluster, all_joints, wdata_list, offset_list):
    """用 OpenMaya API 批量写入权重。"""
    sel = om.MSelectionList()
    sel.add(skin_cluster)
    mobj = om.MObject()
    sel.getDependNode(0, mobj)
    fn_skin = oma.MFnSkinCluster(mobj)

    sel2 = om.MSelectionList()
    sel2.add(mesh)
    dag = om.MDagPath()
    sel2.getDagPath(0, dag)

    jnt_count = len(all_joints)
    total_vtx = cmds.polyEvaluate(mesh, vertex=True)

    inf_indices = om.MIntArray()
    for i in range(jnt_count):
        inf_indices.append(i)

    all_ids = om.MIntArray()
    for i in range(total_vtx):
        all_ids.append(i)

    single_comp = om.MFnSingleIndexedComponent()
    vtx_comp = single_comp.create(om.MFn.kMeshVertComponent)
    single_comp.addElements(all_ids)

    flat = om.MDoubleArray(total_vtx * jnt_count, 0.0)

    jnt_index_map = {}
    for idx, jn in enumerate(all_joints):
        jnt_index_map[jn] = idx

    for part_i, wdata in enumerate(wdata_list):
        offset = offset_list[part_i]
        for local_v, w_dict in enumerate(wdata['weights']):
            base = (offset + local_v) * jnt_count
            for jn, w in w_dict.items():
                ji = jnt_index_map.get(jn)
                if ji is not None:
                    flat[base + ji] = w

    fn_skin.setWeights(dag, vtx_comp, inf_indices, flat, False)


def _is_empty_shell(node):
    """判断 transform 是否为 polyUnite 留下的空壳。"""
    children = cmds.listRelatives(node, children=True, fullPath=True)
    if not children:
        return True
    for child in children:
        if not cmds.objectType(child, isAType='shape'):
            return False
        try:
            if not cmds.getAttr(child + '.intermediateObject'):
                return False
        except Exception:
            return False
    return True


def _most_common_attr(skin_clusters, attr):
    """从多个 skinCluster 中取某属性的最大值，避免截断权重。"""
    values = []
    for sc in skin_clusters:
        try:
            values.append(cmds.getAttr(sc + '.' + attr))
        except Exception:
            pass
    if not values:
        return None
    return max(values)


# ─────────────────────────── 主入口 ───────────────────────────

def merge_selected():
    """
    将选中的多个蒙皮 mesh 合并为一个，保留权重，清理空壳。
    可直接调用，也可绑定到 shelf / 面板按钮。
    """
    t0 = time.time()

    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.inViewMessage(
            amg='<span style="color:#FFD700;">请先选择要合并的模型</span>',
            pos='midCenter', fade=True, fadeStayTime=1500)
        cmds.warning(' 未选择任何对象。')
        return

    # ── 筛选 mesh transform ──
    meshes = []
    for s in sel:
        shapes = cmds.listRelatives(s, shapes=True, noIntermediate=True,
                                    fullPath=True) or []
        if any(cmds.objectType(sh) == 'mesh' for sh in shapes):
            meshes.append(s)

    if len(meshes) < 2:
        cmds.inViewMessage(
            amg='<span style="color:#FFD700;">请至少选择 2 个蒙皮模型</span>',
            pos='midCenter', fade=True, fadeStayTime=1500)
        cmds.warning(' 至少需要 2 个 mesh。')
        return

    # ── BlendShape 检测（收集名字，不阻断） ──
    bs_names = []
    for m in meshes:
        hist = cmds.listHistory(m, pruneDagObjects=True) or []
        if cmds.ls(hist, type='blendShape'):
            bs_names.append(m.split('|')[-1])

    # ══════════════════════ 开启 Undo 块 ══════════════════════
    cmds.undoInfo(openChunk=True, chunkName='MergeSkinnedModels')

    try:
        # ── Step 1: 收集权重 & 骨骼，筛选出有蒙皮的模型 ──
        all_joints_set = set()
        all_joints_short_map = {}
        wdata_list = []
        vtx_counts = []
        skin_clusters = []
        skinned_meshes = []
        skipped_names = []

        for m in meshes:
            sc = _get_skin_cluster(m)
            if not sc:
                short = m.split('|')[-1]
                skipped_names.append(short)
                cmds.warning(
                    ' {} 无 skinCluster，已跳过。'.format(short))
                continue

            skinned_meshes.append(m)
            skin_clusters.append(sc)
            wdata = _get_skin_weights(m, sc)
            wdata_list.append(wdata)
            vtx_counts.append(cmds.polyEvaluate(m, vertex=True))
            for jn in wdata['influences']:
                short_name = jn.split('|')[-1]
                existing = all_joints_short_map.setdefault(short_name, jn)
                if existing != jn:
                    cmds.warning(
                        ' ⚠ 关节短名冲突：{} 和 {} 都叫 {}，权重可能写错骨骼！'
                        .format(existing, jn, short_name))
                all_joints_set.add(jn)

        # ── 有效蒙皮模型不足 2 个 ──
        if len(skinned_meshes) < 2:
            msg = '<span style="color:#FF4444;">合并失败：有效蒙皮不足 2 个</span>'
            if skipped_names:
                msg += '  |  <span style="color:#FFD700;">无蒙皮模型：</span>{}'.format(
                    ', '.join(skipped_names))
            cmds.inViewMessage(amg=msg, pos='midCenter',
                               fade=True, fadeStayTime=1500)
            cmds.warning(' 有效蒙皮模型不足 2 个。')
            return

        all_joints = sorted(all_joints_set)

        # ── 动态读取 maxInfluences ──
        max_inf = _most_common_attr(skin_clusters, 'maxInfluences') or 4

        # ── Step 2: 只复制有蒙皮的模型，用 long name 记录副本 ──
        dupes = []
        for m in skinned_meshes:
            dup = cmds.duplicate(m, returnRootsOnly=True)[0]
            dup_long = cmds.ls(dup, long=True)[0]
            dup_sc = _get_skin_cluster(dup_long)
            if dup_sc:
                cmds.delete(dup_sc)
            dupes.append(dup_long)

        # ── Step 3: polyUnite ──
        united = cmds.polyUnite(dupes, constructionHistory=False,
                                mergeUVSets=True)
        merged_mesh = united[0]

        # ── Step 4: 创建新 skinCluster ──
        new_sc = cmds.skinCluster(
            all_joints, merged_mesh,
            toSelectedBones=True,
            bindMethod=0,
            skinMethod=0,
            normalizeWeights=1,
            maximumInfluences=max_inf,
            obeyMaxInfluences=True,
            removeUnusedInfluence=False,
            name='mergedSkinCluster'
        )[0]

        # ── Step 5: 写入权重 ──
        offset_list = []
        offset = 0
        for vc in vtx_counts:
            offset_list.append(offset)
            offset += vc

        _set_skin_weights(merged_mesh, new_sc, all_joints,
                          wdata_list, offset_list)

        # ── Step 6: 恢复 bindPose ──
        try:
            cmds.dagPose(merged_mesh, restore=True, bindPose=True,
                         **{'g': True})
        except Exception:
            pass

        # ── Step 7: 清理 duplicate 产生的空壳 ──
        for dup_node in dupes:
            if cmds.objExists(dup_node) and _is_empty_shell(dup_node):
                cmds.delete(dup_node)

        # ── Step 8: 命名 & 选中 ──
        short_name = skinned_meshes[0].split('|')[-1]
        merged_mesh = cmds.rename(merged_mesh, short_name + '_merged')
        cmds.select(merged_mesh, r=True)

        elapsed = time.time() - t0

        # ── 合并完成通知 ──
        msg = '<span style="color:#00FF00;">合并完成：</span>{} 个模型 → {}'.format(
            len(skinned_meshes), merged_mesh)
        if skipped_names:
            msg += '  |  <span style="color:#FFD700;">跳过无蒙皮：</span>{}'.format(
                ', '.join(skipped_names))
        if bs_names:
            msg += '  |  <span style="color:#FF4444;">BS丢失：</span>{}'.format(
                ', '.join(bs_names))
        cmds.inViewMessage(amg=msg, pos='midCenter',
                           fade=True, fadeStayTime=1500)

        # ── Script Editor 输出 ──
        print(' 合并完成 → {}  耗时 {:.2f}s'.format(
            merged_mesh, elapsed))
        if skipped_names:
            cmds.warning(' {} 无 skinCluster，已跳过。'.format(
                '、'.join(skipped_names)))
        if bs_names:
            cmds.warning(' {} 含有 BlendShape，合并后 BS 已丢失。'.format(
                '、'.join(bs_names)))

    except Exception as e:
        cmds.warning('MergeSkinnedModels 出错: {}'.format(e))
        raise

    finally:
        cmds.undoInfo(closeChunk=True)