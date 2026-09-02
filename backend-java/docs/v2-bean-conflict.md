# v2 Spring context conflict

## Failing baseline

The earlier full-module run reported 110 tests, 0 failures, and 3 errors:

1. `com.dlxyuki.wms.system.HealthControllerTest#reportsExpectedHealth`
   failed while loading the application context.
2. `com.dlxyuki.wms.system.HealthControllerTest#masterDataRequiresBearerToken`
   failed while loading the same application context.
3. `com.yuki.wms.v2.V2WebContractTest` failed during Spring Boot configuration discovery.

The first cause was a `BeanDefinitionOverrideException`: both
`com.dlxyuki.wms.system.HealthController` and
`com.yuki.wms.v2.controller.HealthController` used the default bean name
`healthController` after both package trees were included in the application scan.

The v2 test cause was the absence of an unambiguous
`@SpringBootConfiguration` in the v2 package hierarchy. The v2 test must load the
module's single application class explicitly rather than trying to discover a
second v2 application.

## Isolation present in the current source

- `com.dlxyuki.wms.WmsApplication` is the only `@SpringBootApplication` and
  explicitly scans `com.dlxyuki.wms` and `com.yuki.wms`.
- The v2 health controller has the distinct bean name `v2HealthController`.
- `V2WebContractTest` and `ReportingReadMapperContractTest` explicitly use
  `@SpringBootTest(classes = WmsApplication.class)`.
- The v2 MyBatis mapper package is registered by the single application class;
  no second `DataSource` or `SqlSessionFactory` configuration is declared.
- The v2 controllers remain under `/api/v2/**` and expose GET routes only.

## Verification

On 2026-09-02, `mvn -q test` completed successfully with 112 tests,
0 failures, 0 errors, and 0 skipped tests. Flyway remains disabled.

No FBA controller, service, repository, or contract-test source was changed as
part of this Spring context diagnosis.
