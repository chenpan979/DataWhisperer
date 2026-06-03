from app.tools.file_store import FileStoreConfig, ManagedFileStore


def test_managed_file_store_saves_lists_previews_and_deletes_file(tmp_path) -> None:
    store = ManagedFileStore(
        FileStoreConfig(
            category="schema",
            directory=tmp_path,
            allowed_extensions=frozenset({".sql"}),
        )
    )

    saved = store.save(
        original_name="orders_schema.sql",
        content=b"CREATE TABLE orders (order_id INT PRIMARY KEY);",
    )

    files = store.list_files()
    preview = store.preview(saved.id)

    assert len(files) == 1
    assert files[0].name == "orders_schema.sql"
    assert files[0].previewable is True
    assert preview is not None
    assert "CREATE TABLE orders" in (preview.preview or "")
    assert store.delete(saved.id) is True
    assert store.list_files() == []


def test_managed_file_store_rejects_unsupported_extension(tmp_path) -> None:
    store = ManagedFileStore(
        FileStoreConfig(
            category="rag",
            directory=tmp_path,
            allowed_extensions=frozenset({".md"}),
        )
    )

    try:
        store.save(original_name="notes.exe", content=b"not allowed")
    except ValueError as exc:
        assert "不支持的文件类型" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Unsupported extension should be rejected.")


def test_managed_file_store_ignores_unsafe_file_id(tmp_path) -> None:
    store = ManagedFileStore(
        FileStoreConfig(
            category="schema",
            directory=tmp_path,
            allowed_extensions=frozenset({".txt"}),
        )
    )

    assert store.delete("../outside") is False
    assert store.preview("../outside") is None
