package com.dlxyuki.wms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WmsApplication {
    public static void main(String[] args) { SpringApplication.run(WmsApplication.class, args); }
}
