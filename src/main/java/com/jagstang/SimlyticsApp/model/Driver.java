package com.jagstang.SimlyticsApp.model;

import jakarta.persistence.*;

import java.util.ArrayList;
import java.util.List;

@Entity
public class Driver {
    @Id
    int driverId;
    String driverName;
    String memberSince;
    String nationality;

    @OneToMany(mappedBy = "driver", cascade = CascadeType.ALL, orphanRemoval = true)
    List<LeagueEntry> leagueEntries = new ArrayList<>();

    @OneToMany(mappedBy = "driver", cascade = CascadeType.ALL, orphanRemoval = true)
    List<License> licenses = new ArrayList<>();

    public Driver() {}

    public Driver(int driverId, String driverName, String memberSince, String nationality, List<LeagueEntry> leagueEntries) {
        this.driverId = driverId;
        this.driverName = driverName;
        this.memberSince = memberSince;
        this.nationality = nationality;
        this.leagueEntries = leagueEntries;
    }

    public int getDriverId() {
        return driverId;
    }

    @Override
    public String toString() {
        return "Driver{" +
                "driverId=" + driverId +
                ", driverName='" + driverName + '\'' +
                ", memberSince='" + memberSince + '\'' +
                ", nationality='" + nationality + '\'' +
                ", leagueEntry=" + leagueEntries +
                '}';
    }

    public int getDriverID() {
        return driverId;
    }
}
