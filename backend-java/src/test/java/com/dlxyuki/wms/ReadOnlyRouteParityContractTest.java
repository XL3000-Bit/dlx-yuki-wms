package com.dlxyuki.wms;

import com.dlxyuki.wms.companyprofile.CompanyProfileController;
import com.dlxyuki.wms.containertracking.ContainerTrackingController;
import com.dlxyuki.wms.dashboard.OperationsDashboardController;
import com.dlxyuki.wms.document.OperationalDocumentController;
import com.dlxyuki.wms.document.OperationalDocumentDownloadController;
import com.dlxyuki.wms.fba.FbaController;
import com.dlxyuki.wms.fba.FbaExportController;
import com.dlxyuki.wms.imports.ImportReadController;
import com.dlxyuki.wms.inbound.InboundController;
import com.dlxyuki.wms.inbound.InboundExportController;
import com.dlxyuki.wms.inbound.InboundTemplateController;
import com.dlxyuki.wms.inventory.InventoryController;
import com.dlxyuki.wms.inventory.InventoryExportController;
import com.dlxyuki.wms.load.LoadController;
import com.dlxyuki.wms.master.MasterDataController;
import com.dlxyuki.wms.notification.NotificationController;
import com.dlxyuki.wms.operationalexception.OperationalExceptionController;
import com.dlxyuki.wms.outbound.OutboundController;
import com.dlxyuki.wms.outbound.OutboundExportController;
import com.dlxyuki.wms.pickingbol.BolController;
import com.dlxyuki.wms.pickingbol.PickingBolController;
import com.dlxyuki.wms.search.SearchController;
import com.dlxyuki.wms.user.UserController;
import com.dlxyuki.wms.workorder.WorkOrderController;
import java.lang.reflect.Method;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

import static org.assertj.core.api.Assertions.assertThat;

class ReadOnlyRouteParityContractTest {
    private static final Pattern PATH_VARIABLE = Pattern.compile("\\{[^/]+}");

    @Test
    void everyRouterMountedFastApiGetHasAJavaMapping() {
        Set<String> actual = getRoutes(List.of(
                UserController.class, MasterDataController.class,
                InboundController.class, InboundExportController.class, InboundTemplateController.class,
                ImportReadController.class,
                InventoryController.class, InventoryExportController.class,
                FbaController.class, classForName("com.dlxyuki.wms.fba.FbaAllocationController"), FbaExportController.class,
                OutboundController.class, OutboundExportController.class,
                PickingBolController.class, BolController.class,
                ContainerTrackingController.class, SearchController.class,
                LoadController.class, WorkOrderController.class,
                OperationalExceptionController.class,
                OperationalDocumentController.class, OperationalDocumentDownloadController.class,
                OperationsDashboardController.class, NotificationController.class,
                CompanyProfileController.class));

        assertThat(actual).containsAll(Set.of(
                "/api/v1/users", "/api/v1/users/me",
                "/api/v1/master-data/customers", "/api/v1/master-data/warehouses",
                "/api/v1/master-data/warehouse-areas", "/api/v1/master-data/warehouse-locations",
                "/api/v1/master-data/carriers", "/api/v1/master-data/amazon-fc-addresses",
                "/api/v1/master-data/amazon-fc-addresses/{id}",
                "/api/v1/inbound", "/api/v1/inbound/{id}",
                "/api/v1/inbound/files/template.xlsx", "/api/v1/inbound/files/export.xlsx",
                "/api/v1/imports/profiles", "/api/v1/imports", "/api/v1/imports/{id}",
                "/api/v1/imports/{id}/progress", "/api/v1/imports/{id}/validation-result",
                "/api/v1/imports/{id}/errors.xlsx", "/api/v1/imports/{id}/errors",
                "/api/v1/imports/{id}/rows",
                "/api/v1/inventory", "/api/v1/inventory/{id}",
                "/api/v1/inventory/{id}/transactions", "/api/v1/inventory/files/export.xlsx",
                "/api/v1/fba", "/api/v1/fba/workbench", "/api/v1/fba/{id}",
                "/api/v1/fba/{id}/workbench-detail", "/api/v1/fba/{id}/allocations",
                "/api/v1/fba/files/export.xlsx",
                "/api/v1/outbounds", "/api/v1/outbounds/workbench", "/api/v1/outbounds/{id}",
                "/api/v1/outbounds/{id}/workbench-detail", "/api/v1/outbounds/{id}/dispatch-readiness",
                "/api/v1/outbounds/{id}/allocations", "/api/v1/outbounds/files/export.xlsx",
                "/api/v1/picking-lists", "/api/v1/picking-lists/{id}",
                "/api/v1/picking-lists/{id}/xlsx",
                "/api/v1/bols", "/api/v1/bols/{id}", "/api/v1/bols/{id}/xlsx", "/api/v1/bols/{id}/pdf",
                "/api/v1/container-tracking", "/api/v1/container-tracking/{id}",
                "/api/v1/search",
                "/api/v1/loads", "/api/v1/loads/{id}", "/api/v1/loads/{id}/execution-summary",
                "/api/v1/work-orders", "/api/v1/work-orders/{id}", "/api/v1/work-orders/{id}/events",
                "/api/v1/operational-exceptions", "/api/v1/operational-exceptions/{id}",
                "/api/v1/operational-exceptions/{id}/events",
                "/api/v1/documents", "/api/v1/documents/{id}", "/api/v1/documents/{id}/events",
                "/api/v1/documents/{id}/download",
                "/api/v1/dashboard/operations",
                "/api/v1/notifications", "/api/v1/notifications/unread-count",
                "/api/v1/company-profile"));
    }

    private static Set<String> getRoutes(List<Class<?>> controllers) {
        Set<String> routes = new HashSet<>();
        for (Class<?> controller : controllers) {
            String prefix = first(controller.getAnnotation(RequestMapping.class).value());
            for (Method method : controller.getDeclaredMethods()) {
                GetMapping get = method.getAnnotation(GetMapping.class);
                if (get != null) {
                    routes.add(normalize(prefix + first(get.value())));
                }
            }
        }
        return routes;
    }

    private static String first(String[] paths) {
        return paths.length == 0 ? "" : paths[0];
    }

    private static String normalize(String path) {
        return PATH_VARIABLE.matcher(path).replaceAll("{id}");
    }

    private static Class<?> classForName(String name) {
        try {
            return Class.forName(name);
        } catch (ClassNotFoundException exception) {
            throw new AssertionError("Controller class not found: " + name, exception);
        }
    }
}
