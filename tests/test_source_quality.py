from src.source_quality import classify_source_label, source_status_table


def test_classify_uploaded_source_is_user_dependent():
    status = classify_source_label("Uploaded CSV")

    assert status.category == "Uploaded / analyst supplied"
    assert status.confidence == "User dependent"


def test_classify_bundled_synthetic_source_is_low_confidence():
    status = classify_source_label("Bundled synthetic regional generation mix")

    assert status.category == "Synthetic sample"
    assert status.confidence == "Low"


def test_source_status_table_keeps_dataset_names():
    table = source_status_table({"Forward curves": "Live public sources"})

    assert table.loc[0, "dataset"] == "Forward curves"
    assert table.loc[0, "category"] == "Public / derived live feed"
