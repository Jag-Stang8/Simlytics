package com.jagstang.SimlyticsApp;

import org.springframework.boot.SpringApplication;

public class TestSimlyticsApplication {

	public static void main(String[] args) {
		SpringApplication.from(SimlyticsApplication::main).with(TestcontainersConfiguration.class).run(args);
	}

}
