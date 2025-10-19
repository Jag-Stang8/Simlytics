package com.jagstang.SimlyticsApp.model;

import jakarta.persistence.*;

@Entity
public class License {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int licenseId;

    private String licenseName;
    private int licenseLevel;
    private double safetyRating;
    private double cpi;
    private int irating;
    private int ttRating;
    private int mprNumRaces;
    private String color;
    private String groupName;
    private int groupId;

    @ManyToOne
    @JoinColumn(name = "driver_Id", nullable = false)
    private Driver driver;

    public License() {}

    public License(String licenseName, int licenseLevel, double safetyRating, double cpi, int irating, int ttRating, int mprNumRaces, String color, String groupName, int groupId, Driver driver) {
        this.licenseName = licenseName;
        this.licenseLevel = licenseLevel;
        this.safetyRating = safetyRating;
        this.cpi = cpi;
        this.irating = irating;
        this.ttRating = ttRating;
        this.mprNumRaces = mprNumRaces;
        this.color = color;
        this.groupName = groupName;
        this.groupId = groupId;
        this.driver = driver;
    }

    @Override
    public String toString() {
        return "License{" +
                "licenseId=" + licenseId +
                ", licenseName='" + licenseName + '\'' +
                ", licenseLevel=" + licenseLevel +
                ", safetyRating=" + safetyRating +
                ", cpi=" + cpi +
                ", irating=" + irating +
                ", ttRating=" + ttRating +
                ", mprNumRaces=" + mprNumRaces +
                ", color='" + color + '\'' +
                ", groupName='" + groupName + '\'' +
                ", groupId=" + groupId +
                ", driver=" + driver +
                '}';
    }
}
