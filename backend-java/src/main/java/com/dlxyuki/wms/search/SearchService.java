package com.dlxyuki.wms.search;

import com.dlxyuki.wms.user.UserAccount;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class SearchService {
    private final SearchRepository repository;
    public SearchService(SearchRepository repository) { this.repository = repository; }

    public Map<String,Object> search(String query, int limit, UserAccount user) {
        int cap = Math.min(Math.max(limit * 3, 20), 150);
        List<SearchRepository.Candidate> candidates = new ArrayList<>(repository.search(query, cap, user));
        candidates.sort(Comparator.comparingInt(SearchRepository.Candidate::rank)
            .thenComparingInt(SearchRepository.Candidate::groupOrder)
            .thenComparingLong(SearchRepository.Candidate::id));
        List<SearchRepository.Candidate> selected = candidates.stream().limit(limit).toList();
        List<Map<String,Object>> groups = new ArrayList<>();
        for (String type : SearchRepository.TYPES) {
            List<Map<String,Object>> items = selected.stream().filter(c -> c.type().equals(type))
                .map(SearchService::item).toList();
            if (!items.isEmpty()) groups.add(Map.of("type", type, "count", items.size(), "items", items));
        }
        Map<String,Object> result = new LinkedHashMap<>();
        result.put("query", query); result.put("total", selected.size()); result.put("groups", groups);
        return result;
    }

    private static Map<String,Object> item(SearchRepository.Candidate c) {
        Map<String,Object> row = new LinkedHashMap<>();
        row.put("type", c.type()); row.put("id", c.id()); row.put("primary_reference", c.primary());
        row.put("secondary_reference", c.secondary()); row.put("status", c.status());
        row.put("warehouse", c.warehouse()); row.put("customer", c.customer());
        row.put("target_route", c.route()); row.put("match_rank", c.rank()); return row;
    }
}
