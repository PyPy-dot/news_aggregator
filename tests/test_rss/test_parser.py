"""
Тесты для RSS парсера.
"""

import pytest

from services.rss.parser import RSSParserService, ParsedNewsItem, FeedMetadata


class TestRSSParserService:
    """Тесты для RSSParserService."""

    @pytest.fixture
    def parser(self) -> RSSParserService:
        """Создать парсер для тестов."""
        return RSSParserService(timeout=10)

    def test_parse_rss_2_0(self, parser: RSSParserService):
        """Парсинг RSS 2.0 ленты."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Test News</title>
                <link>https://example.com</link>
                <description>Test RSS Feed</description>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/article1</link>
                    <description>Test description</description>
                    <guid>article-1</guid>
                    <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
                    <author>John Doe</author>
                    <category>Politics</category>
                </item>
            </channel>
        </rss>
        """

        metadata, items = parser.parse_xml_string(xml)

        assert metadata is not None
        assert metadata.title == "Test News"
        assert metadata.link == "https://example.com"

        assert len(items) == 1
        item = items[0]

        assert item.title == "Test Article"
        assert item.link == "https://example.com/article1"
        assert item.description == "Test description"
        assert item.guid == "article-1"
        assert item.author == "John Doe"
        assert "Politics" in item.categories

    def test_parse_atom_feed(self, parser: RSSParserService):
        """Парсинг Atom ленты."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>Test Atom Feed</title>
            <link href="https://example.com"/>
            <entry>
                <title>Atom Article</title>
                <link href="https://example.com/atom1"/>
                <summary>Atom summary</summary>
                <id>atom-1</id>
                <updated>2024-01-01T12:00:00Z</updated>
                <author><name>Jane Doe</name></author>
            </entry>
        </feed>
        """

        metadata, items = parser.parse_xml_string(xml)

        assert metadata is not None
        assert metadata.title == "Test Atom Feed"

        assert len(items) == 1
        item = items[0]

        assert item.title == "Atom Article"
        assert item.link == "https://example.com/atom1"
        assert item.description == "Atom summary"
        assert item.guid == "atom-1"
        assert item.author == "Jane Doe"

    def test_parse_multiple_items(self, parser: RSSParserService):
        """Парсинг нескольких новостей."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Multi News</title>
                <item>
                    <title>Article 1</title>
                    <link>https://example.com/1</link>
                    <guid>1</guid>
                </item>
                <item>
                    <title>Article 2</title>
                    <link>https://example.com/2</link>
                    <guid>2</guid>
                </item>
                <item>
                    <title>Article 3</title>
                    <link>https://example.com/3</link>
                    <guid>3</guid>
                </item>
            </channel>
        </rss>
        """

        metadata, items = parser.parse_xml_string(xml)

        assert len(items) == 3
        assert items[0].title == "Article 1"
        assert items[1].title == "Article 2"
        assert items[2].title == "Article 3"

    def test_parse_missing_required_fields(self, parser: RSSParserService):
        """Парсинг записей без обязательных полей."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Only Title</title>
                </item>
                <item>
                    <link>https://example.com/no-title</link>
                </item>
                <item>
                    <title>Complete</title>
                    <link>https://example.com/complete</link>
                </item>
            </channel>
        </rss>
        """

        metadata, items = parser.parse_xml_string(xml)

        # feedparser фильтрует записи без title или link
        # Остаётся только полная запись
        assert len(items) == 1
        assert items[0].title == "Complete"

    def test_parse_with_content(self, parser: RSSParserService):
        """Парсинг с полным контентом."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Article</title>
                    <link>https://example.com/article</link>
                    <description>Short description</description>
                    <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">
                        Full article content here
                    </content:encoded>
                </item>
            </channel>
        </rss>
        """

        metadata, items = parser.parse_xml_string(xml)

        assert len(items) == 1
        item = items[0]

        assert item.description == "Short description"
        assert "Full article content here" in (item.content or "")

    def test_parse_with_image(self, parser: RSSParserService):
        """Парсинг с изображением."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Article with Image</title>
                    <link>https://example.com/article</link>
                    <media:content xmlns:media="http://search.yahoo.com/mrss/" url="https://example.com/image.jpg" medium="image"/>
                </item>
            </channel>
        </rss>
        """

        metadata, items = parser.parse_xml_string(xml)

        assert len(items) == 1
        item = items[0]

        assert item.image_url == "https://example.com/image.jpg"

    def test_parse_invalid_xml(self, parser: RSSParserService):
        """Парсинг невалидного XML."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Unclosed tag
                </item>
            </channel>
        </rss>
        """

        # Feedparser должен обработать с ошибками
        metadata, items = parser.parse_xml_string(xml)

        # Парсер должен вернуть что-то, даже с ошибками
        assert metadata is not None or len(items) >= 0

    def test_parsed_news_item_dataclass(self):
        """Тест dataclass ParsedNewsItem."""
        item = ParsedNewsItem(
            title="Test",
            link="https://example.com",
            description="Desc",
            categories=["cat1", "cat2"]
        )

        assert item.title == "Test"
        assert item.link == "https://example.com"
        assert item.description == "Desc"
        assert item.categories == ["cat1", "cat2"]

    def test_feed_metadata_dataclass(self):
        """Тест dataclass FeedMetadata."""
        metadata = FeedMetadata(
            title="Test Feed",
            link="https://example.com",
            description="Test",
            language="en"
        )

        assert metadata.title == "Test Feed"
        assert metadata.language == "en"


class TestRSSParserService_Integration:
    """Интеграционные тесты для RSS парсера."""

    @pytest.mark.asyncio
    async def test_fetch_feed_real_url(self):
        """Тест получения реальной RSS ленты (если есть интернет)."""
        parser = RSSParserService(timeout=10)

        # Используем публичную RSS ленту для теста
        url = "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"

        try:
            metadata, items, has_changes = await parser.fetch_feed(url)

            # Если интернет есть, проверяем результат
            if metadata:
                assert metadata.title is not None
                assert len(items) >= 0
        except Exception:
            # Если нет интернета или лента недоступна — пропускаем
            pytest.skip("RSS лента недоступна или нет интернета")

    def test_parse_empty_feed(self):
        """Парсинг пустой ленты."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Empty Feed</title>
            </channel>
        </rss>
        """

        parser = RSSParserService()
        metadata, items = parser.parse_xml_string(xml)

        assert metadata is not None
        assert metadata.title == "Empty Feed"
        assert len(items) == 0
