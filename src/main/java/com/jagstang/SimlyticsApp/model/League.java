package com.jagstang.SimlyticsApp.model;

import jakarta.persistence.*;

import java.util.ArrayList;
import java.util.List;

@Entity
public class League {
    @Id
    int leagueId;
    String leagueName;
    String created;
    boolean hidden;
    String message;
    String about;
    String url;
    int rosterCount;
    String smallLogo;
    String largeLogo;

    @OneToMany(mappedBy = "league", cascade = CascadeType.ALL, orphanRemoval = true)
    List<LeagueEntry> leagueEntries = new ArrayList<>();

    public League() {}

    public League(int leagueId, String leagueName, String created, boolean hidden, String message, String about, String url, int rosterCount, String smallLogo, String largeLogo) {
        this.leagueId = leagueId;
        this.leagueName = leagueName;
        this.created = created;
        this.hidden = hidden;
        this.message = message;
        this.about = about;
        this.url = url;
        this.rosterCount = rosterCount;
        this.smallLogo = smallLogo;
        this.largeLogo = largeLogo;
    }

    public int getLeagueId() {
        return leagueId;
    }

    public String toString() {
        return "League{" +
                "leagueId=" + leagueId +
                ", leagueName='" + leagueName + '\'' +
                ", created='" + created + '\'' +
                ", hidden=" + hidden +
                ", message='" + message + '\'' +
                ", about='" + about + '\'' +
                ", url='" + url + '\'' +
                ", rosterCount=" + rosterCount +
                ", smallLogo='" + smallLogo + '\'' +
                ", largeLogo='" + largeLogo + '\'' +
                '}';
    }
}
