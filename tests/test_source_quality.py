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


def test_gated_signal_inputs_are_not_labelled_as_sample_history():
    status = classify_source_label("Provenance-gated current observations")
    assert status.category == "Dated public / desk inputs"
    assert "not an independent audit" in status.caveat


def test_mixed_history_is_not_labelled_entirely_synthetic():
    status = classify_source_label("public / synthetic")
    assert status.category == "Mixed public / sample history"


def test_scheduled_news_snapshot_has_publisher_dependent_quality():
    status = classify_source_label("Scheduled public news snapshot")
    assert status.category == "Public news snapshot"
    assert status.confidence == "Publisher dependent"
