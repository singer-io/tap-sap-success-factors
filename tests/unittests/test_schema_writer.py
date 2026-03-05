from unittest.mock import Mock

from tap_sap_success_factors.schema import write_schema


class FakeCatalog:
    streams = []

    def get_stream(self, stream_name):
        del stream_name

        class _Schema:
            @staticmethod
            def to_dict():
                return {
                    "type": "object",
                    "properties": {
                        "personIdExternal": {"type": ["null", "string"]}
                    },
                }

        return Mock(schema=_Schema(), metadata=[{"breadcrumb": [], "metadata": {"selected": True}}])


def test_write_schema_writes_only_selected_stream():
    stream = Mock()
    stream.is_selected.return_value = True
    write_schema(stream, Mock(), ["per_email"], FakeCatalog())

    stream.write_schema.assert_called_once()
