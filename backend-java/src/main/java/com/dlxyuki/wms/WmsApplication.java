package com.dlxyuki.wms;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication(scanBasePackages = {"com.dlxyuki.wms", "com.yuki.wms"})
@ConfigurationPropertiesScan(basePackages = "com.dlxyuki.wms")
@MapperScan("com.yuki.wms.v2.mapper")
public class WmsApplication {
    public static void main(String[] args) { SpringApplication.run(WmsApplication.class, args); }
}
