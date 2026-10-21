import pytest

from udb.integrations.moodle import client, reader


@pytest.mark.parametrize("name", ["mod_forum_add_discussion_post", "mod_assign_save_submission",
                                  "core_message_send_instant_messages", "mod_forum_view_forum",
                                  "core_message_mark_notification_read",
                                  "tool_mobile_get_autologin_key"])
def test_writes_are_refused(name):
    api = reader.ReadOnlyApi("https://moodle.invalid", "t")
    with pytest.raises(client.MoodleError, match="read-only"):
        api.call(name)


def test_reads_pass_the_guard():
    for name in ("gradereport_user_get_grades_table", "mod_forum_get_discussion_posts",
                 "message_popup_get_popup_notifications", "core_course_get_updates_since"):
        assert reader.READ_RE.match(name)


def test_text_keeps_paragraphs_not_source_newlines():
    html = "<p>Hola\r\njóvenes, <b>bienvenidos</b>.</p><ul><li>Uno</li><li>Dos</li></ul>"
    assert reader.text(html) == "Hola jóvenes, bienvenidos.\n- Uno\n- Dos"
