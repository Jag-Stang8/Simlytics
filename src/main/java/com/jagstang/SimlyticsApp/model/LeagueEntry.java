package com.jagstang.SimlyticsApp.model;

import jakarta.persistence.*;

@Entity
public class LeagueEntry {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    int leagueEntryId;

    @ManyToOne
    @JoinColumn(name = "driver_Id", nullable = false)
    Driver driver;

    @ManyToOne
    @JoinColumn(name = "league_Id", nullable = false)
    League league;
}
