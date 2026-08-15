#!/usr/bin/env python3
"""ChromaDB 嵌入维度迁移 CLI。

用法(在项目根目录, 用 venv python 运行):

    .venv-linux/bin/python scripts/migrate_embedding.py --target-dim 768 --dry-run
    .venv-linux/bin/python scripts/migrate_embedding.py --target-dim 768

行为:
- 读取 ``bobanana.config.CHROMA_DB_DIR`` 下所有 collection;
- 参考 ``database.py`` 的 ``_validate_dimension`` 手法检查每条 collection 的嵌入维度;
- 维度与 ``--target-dim N`` 不匹配时:
    * ``--dry-run``: 仅打印迁移计划(新建 collection ``knowledge_cards_dim{N}``),
      不做任何修改;
    * 真实执行: 先自动 ``bobanana.backup.create_backup`` 备份, 然后
      ``get_or_create`` 新 collection, 用 ``bobanana.tools.embed_text`` 以新维度
      重新嵌入并迁移旧数据;
- ``embed_text`` 当前模型维度若 != N, 打印警告并要求先改配置
  (EMBEDDING_DIMENSION / 模型)再跑, 不硬跑迁移。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许脚本作为独立文件直接运行: 把项目根目录加入 sys.path, 以便 import bobanana。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将现有 ChromaDB collection 以新嵌入维度重新嵌入迁移。"
    )
    parser.add_argument(
        "--target-dim",
        type=int,
        required=True,
        help="目标嵌入维度, 例如 768。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印迁移计划, 不做任何修改(不备份、不写库)。",
    )
    return parser.parse_args(argv)


def _collection_dimension(col) -> int | None:
    """参考 database.py ``_validate_dimension`` 的手法: 取一条样本向量长度。

    注意: chromadb 的 ``get(include=["embeddings"])`` 返回 numpy ndarray,
    不能用真值判断, 必须显式判 ``is not None`` 与长度。
    """
    count = col.count()
    if count == 0:
        return None
    sample = col.get(limit=1, include=["embeddings"])
    embeddings = sample.get("embeddings") if sample else None
    if embeddings is not None and len(embeddings) > 0:
        return len(embeddings[0])
    return None


def _probe_model_dim() -> int | None:
    """探测 embed_text 当前模型维度(离线优先, 失败返回 None)。"""
    from bobanana.config import EMBEDDING_PROVIDER
    from bobanana.tools import embed_text, get_embedding_model

    try:
        if EMBEDDING_PROVIDER == "sentence-transformers":
            model = get_embedding_model()
            return int(model.get_embedding_dimension())
        vector = embed_text("__dim_probe__")
        return len(vector)
    except Exception as e:
        print(f"[warn] 无法探测 embed_text 模型维度: {e}")
        return None


def _embedding_text(meta: dict | None, document: str) -> str:
    """按 KnowledgeCard.embedding_text() 的语义重建嵌入文本(title + aliases + content)。"""
    meta = meta or {}
    title = meta.get("title", "") or ""
    aliases_raw = meta.get("aliases", "") or ""
    parts = [title]
    parts.extend(a.strip() for a in aliases_raw.split(",") if a.strip())
    parts.append(document or "")
    return "\n".join(parts)


def _build_plan(client, target: int, default_collection: str) -> list[dict]:
    """扫描所有 collection, 生成维度不匹配时的迁移计划。"""
    plan: list[dict] = []
    for col in client.list_collections():
        actual = _collection_dimension(col)
        if actual is None:
            print(f"[skip] {col.name}: 空 collection, 无需迁移")
            continue
        if actual == target:
            print(f"[skip] {col.name}: 维度已为 {actual}, 无需迁移")
            continue
        if col.name == default_collection:
            new_name = f"{default_collection}_dim{target}"
        else:
            new_name = f"{col.name}_dim{target}"
        plan.append(
            {
                "old": col.name,
                "actual_dim": actual,
                "new": new_name,
                "count": col.count(),
            }
        )
    return plan


def _run_migration(client, plan: list[dict], target: int) -> None:
    """对计划中的每条 collection 执行迁移。"""
    from bobanana.tools import embed_text

    for item in plan:
        old_name = item["old"]
        new_name = item["new"]
        old_col = client.get_collection(old_name)
        # ids 始终返回; include 只需 documents/metadatas(embedding 之后重新生成)
        data = old_col.get(include=["documents", "metadatas"])

        # 归一化为 list(避免 numpy/None 真值歧义)
        ids = list(data.get("ids")) if data.get("ids") is not None else []
        docs = list(data.get("documents")) if data.get("documents") is not None else []
        metas = list(data.get("metadatas")) if data.get("metadatas") is not None else []

        new_col = client.get_or_create_collection(
            name=new_name, metadata={"hnsw:space": "cosine"}
        )

        migrated = 0
        for i, cid in enumerate(ids):
            document = docs[i] if i < len(docs) else ""
            meta = metas[i] if i < len(metas) else None
            text = _embedding_text(meta, document)
            try:
                embedding = embed_text(text or " ")
            except Exception as e:
                print(f"[warn] {cid} 嵌入失败, 跳过: {e}")
                continue
            if len(embedding) != target:
                print(f"[warn] {cid} 生成维度 {len(embedding)} != {target}, 跳过")
                continue
            new_col.add(
                ids=[cid],
                embeddings=[embedding],
                metadatas=[meta] if isinstance(meta, dict) else None,
                documents=[document],
            )
            migrated += 1
            if migrated % 50 == 0:
                print(f"  [{old_name}] 已迁移 {migrated}/{len(ids)}")

        print(f"[done] {old_name} -> {new_name}: 迁移 {migrated}/{len(ids)} 张")


def main(argv=None) -> int:
    args = _parse_args(argv)
    target = args.target_dim
    if target <= 0:
        print("[error] --target-dim 必须为正整数")
        return 2

    import chromadb
    from chromadb.config import Settings

    from bobanana.config import (
        CHROMA_COLLECTION_NAME,
        CHROMA_DB_DIR,
        EMBEDDING_DIMENSION,
    )

    client = chromadb.PersistentClient(
        path=str(CHROMA_DB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    # 探测当前 embed_text 模型维度(仅报告, dry-run 不据此中止)
    model_dim = _probe_model_dim()

    plan = _build_plan(client, target, CHROMA_COLLECTION_NAME)

    if not plan:
        print("没有需要迁移的 collection。")
        return 0

    print("=" * 60)
    print(f"迁移计划 (target-dim={target}):")
    for item in plan:
        print(
            f"  {item['old']} (dim={item['actual_dim']}, {item['count']} 张) "
            f"-> {item['new']}"
        )
    print("=" * 60)

    if args.dry_run:
        if model_dim is not None and model_dim != target:
            print(
                f"[warn] 当前 embed_text 模型维度={model_dim} != 目标维度={target}。"
                "真实迁移前请先修改配置。"
            )
        print("[dry-run] 不做任何修改。")
        return 0

    # ── 真实执行前的模型维度校验 ────────────────────
    if model_dim is None:
        print(
            "[error] 无法确认 embed_text 模型维度。为避免写入错误维度, "
            "请先修复模型加载或配置后重跑, 不硬跑迁移。"
        )
        return 1
    if model_dim != target:
        print(
            f"[error] 当前 embed_text 模型维度={model_dim} != 目标维度={target}。"
            "请先修改配置(EMBEDDING_DIMENSION 与对应模型)再重跑, 不硬跑迁移。"
        )
        return 1
    if target != EMBEDDING_DIMENSION:
        print(
            f"[warn] 目标维度 {target} != config.EMBEDDING_DIMENSION={EMBEDDING_DIMENSION}。"
            "迁移完成后请同步更新 .env 的 EMBEDDING_DIMENSION 并重启服务。"
        )

    # ── 自动备份当前状态 ────────────────────────────
    from bobanana.backup import create_backup

    try:
        backup_path = create_backup()
        print(f"[backup] 已创建备份: {backup_path}")
    except Exception as e:
        print(f"[error] 迁移前备份失败, 中止: {e}")
        return 1

    # ── 执行迁移 ────────────────────────────────────
    try:
        _run_migration(client, plan, target)
    except Exception as e:
        print(f"[error] 迁移失败: {e}")
        return 1

    print("迁移完成。请更新 .env 的 EMBEDDING_DIMENSION 并重启服务以使用新 collection。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
