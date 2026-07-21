class MemoryReadService:
    def _build_filtered_query(self, query, filters):
        if query:
            query = query.strip()
        if filters:
            filter_str = ' '.join(f'#{key}:{value}' for key, value in filters.items())
            if query:
                return f'{query} {filter_str}'
            else:
                return filter_str
        return query

def test_filtered_query_no_leading_space():
    service = MemoryReadService()
    query = ''
    filters = {'memory_type': 'fact'}
    result = service._build_filtered_query(query, filters)
    assert result == '#memory_type:fact'

    query = '   '
    result = service._build_filtered_query(query, filters)
    assert result == '#memory_type:fact'

    query = 'test'
    result = service._build_filtered_query(query, filters)
    assert result == 'test #memory_type:fact'