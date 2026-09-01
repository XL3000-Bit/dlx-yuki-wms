package com.dlxyuki.wms.inbound;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.user.*;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDate;
import java.time.ZoneId;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InboundService {
    private final InboundRepository repository;
    private final ObjectMapper json;
    public InboundService(InboundRepository repository, ObjectMapper json) { this.repository = repository; this.json = json; }

    public InboundListResponse list(InboundQuery query, UserAccount user) { return repository.list(query, user); }
    public InboundResponse get(long id, UserAccount user) { return repository.find(id, user).orElseThrow(this::notFound); }

    @Transactional
    public InboundResponse create(InboundRequest request, UserAccount user) {
        requireWriter(user); assertScope(request, user); validateReferences(request);
        long id = repository.insert(request, user.id(), LocalDate.now(ZoneId.of("America/Los_Angeles")));
        repository.audit(user.id(), "CREATE", id, null, encode(request));
        return repository.find(id, user).orElseThrow(this::notFound);
    }

    @Transactional
    public InboundResponse update(long id, InboundRequest request, UserAccount user) {
        requireWriter(user); assertScope(request, user);
        InboundResponse before = get(id, user);
        validateReferences(request);
        repository.update(id, request);
        repository.audit(user.id(), "UPDATE", id, encode(before), encode(request));
        return repository.find(id, user).orElseThrow(this::notFound);
    }

    private void validateReferences(InboundRequest request) {
        if (!repository.warehouseExists(request.warehouseId())) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Warehouse not found");
        if (request.customerId() != null && !repository.customerExists(request.customerId())) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Customer not found");
        if (request.locationId() != null && !repository.locationMatches(request.locationId(), request.warehouseId())) throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Location does not belong to warehouse");
    }
    private void assertScope(InboundRequest request, UserAccount user) {
        if (!"ADMIN".equals(user.role()) && "SELECTED".equals(user.warehouseScopeMode()) && !user.warehouseIds().contains(request.warehouseId()))
            throw new ApiException(HttpStatus.FORBIDDEN, "Warehouse is outside your assigned scope");
        if (request.customerId() != null && !"ADMIN".equals(user.role()) && "SELECTED".equals(user.customerScopeMode()) && !user.customerIds().contains(request.customerId()))
            throw new ApiException(HttpStatus.FORBIDDEN, "Customer is outside your assigned scope");
    }
    private void requireWriter(UserAccount user) {
        if (!Permissions.forRole(user.role()).contains("manage_inbound")) throw new ApiException(HttpStatus.FORBIDDEN, "Warehouse write permission required");
    }
    private String encode(Object value) { try { return json.writeValueAsString(value); } catch (JsonProcessingException e) { throw new IllegalStateException("Could not serialize audit data", e); } }
    private ApiException notFound() { return new ApiException(HttpStatus.NOT_FOUND, "Inbound record not found"); }
}
