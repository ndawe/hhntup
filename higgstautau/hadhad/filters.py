from rootpy.tree.filtering import EventFilter
from atlastools import utils
from atlastools.units import GeV
from atlastools import datasets
from math import *
from .models import TrueTauBlock
from . import track_counting
from .. import tauid


class TauLeadSublead(EventFilter):

    def __init__(self, lead=35*GeV, sublead=25*GeV, **kwargs):

        super(TauLeadSublead, self).__init__(**kwargs)
        """
        Leading and subleading tau pT thresholds
        """
        self.lead = lead
        self.sublead = sublead

    def passes(self, event):
        # sort in descending order by pT
        event.taus.sort(key=lambda tau: tau.pt, reverse=True)
        # only keep leading two taus
        event.taus.slice(0, 2)
        # Event passes if the highest pT tau is above the leading
        # pT threshold and the next subleading tau pT is above the subleading pT theshold
        return event.taus[0].pt > self.lead and event.taus[1].pt > self.sublead


class Triggers(EventFilter):
    """
    See lowest unprescaled triggers here:
    https://twiki.cern.ch/twiki/bin/viewauth/Atlas/LowestUnprescaled#Taus_electron_muon_MET
    """
    def __init__(self, year, old_skim=False, **kwargs):

        if year == 2011:
            if old_skim:
                self.passes = self.passes_11_old
            else:
                self.passes = self.passes_11
        elif year == 2012:
            self.passes = self.passes_12
        else:
            raise ValueError("No triggers defined for year %d" % year)
        super(Triggers, self).__init__(**kwargs)

    def passes_11(self, event):
        try:
            if 177986 <= event.RunNumber <= 187815: # Periods B-K
                return event.EF_tau29_medium1_tau20_medium1
            elif 188902 <= event.RunNumber <= 191933: # Periods L-M
                return event.EF_tau29T_medium1_tau20T_medium1
        except AttributeError, e:
            print "Missing trigger for run %i: %s" % (event.RunNumber, e)
            raise e
        raise ValueError("No trigger condition defined for run %s" % event.RunNumber)

    def passes_11_old(self, event):
        try:
            if 177986 <= event.RunNumber <= 187815: # Periods B-K
                return event.EF_tau29_medium1_tau20_medium1_EMULATED
            elif 188902 <= event.RunNumber <= 191933: # Periods L-M
                return event.EF_tau29T_medium1_tau20T_medium1_EMULATED
        except AttributeError, e:
            print "Missing trigger for run %i: %s" % (event.RunNumber, e)
            raise e
        raise ValueError("No trigger condition defined for run %s" % event.RunNumber)

    def passes_12(self, event):
        try:
            return event.EF_tau29Ti_medium1_tau20Ti_medium1
        except AttributeError, e:
            print "Missing trigger for run %i: %s" % (event.RunNumber, e)
            raise e

        # TODO use tau27Ti_m1_tau18Ti_m1_L2loose for period E
        # need emulaion, SFs for this


class ElectronVeto(EventFilter):

    def passes(self, event):

        for el in event.electrons:
            pt = el.cl_E / cosh(el.tracketa)
            if pt <= 15 * GeV: continue
            if not ((abs(el.tracketa) < 1.37) or (1.52 < abs(el.tracketa) < 2.47)): continue
            if el.author not in (1, 3): continue
            if not abs(el.charge) == 1: continue
            if el.mediumPP != 1: continue
            if (el.OQ & 1446) != 0: continue
            return False
        return True


from ..filters import muon_has_good_track

class MuonVeto(EventFilter):

    def __init__(self, year, **kwargs):

        self.year = year
        super(MuonVeto, self).__init__(**kwargs)

    def passes(self, event):

       for muon in event.muons:
           if muon.pt <= 10 * GeV:
               continue
           if abs(muon.eta) >= 2.5:
               continue
           if muon.loose != 1:
               continue
           if not muon_has_good_track(muon, self.year):
               continue
           return False
       return True


class TaudR(EventFilter):

    def __init__(self, dr=3.2, **kwargs):

        super(TaudR, self).__init__(**kwargs)
        self.dr = dr

    def passes(self, event):

        assert len(event.taus) == 2
        tau1, tau2 = event.taus
        return utils.dR(tau1.eta, tau1.phi, tau2.eta, tau2.phi) < self.dr


class TruthMatching(EventFilter):

    def passes(self, event):

        for tau in event.taus:
            if tau.trueTauAssoc_index > -1:
                tau.matched = True
        return True


class TauTrackRecounting(EventFilter):

    def __init__(self, year, **kwargs):

        self.year = year
        super(TauTrackRecounting, self).__init__(**kwargs)

    def passes(self, event):

        for tau in event.taus:
            tau.numTrack_recounted = track_counting.count_tracks(
                    tau, event, self.year)
        return True


class EfficiencyScaleFactors(EventFilter):

    def __init__(self, year, **kwargs):

        self.year = year
        super(EfficiencyScaleFactors, self).__init__(**kwargs)

    def passes(self, event):

        for tau in event.taus:
            if tau.matched:
                # efficiency scale factor
                effic_sf, err = tauid.effic_sf_uncert(tau, self.year)
                tau.efficiency_scale_factor = effic_sf
                # ALREADY ACCOUNTED FOR IN TauBDT SYSTEMATIC
                tau.efficiency_scale_factor_high = effic_sf + err
                tau.efficiency_scale_factor_low = effic_sf - err
        return True


class FakeRateScaleFactors(EventFilter):

    def __init__(self, year, passthrough=False, **kwargs):

        if not passthrough:
            self.year = year % 1000
            if self.year == 11:
                from externaltools.bundle_2011 import TauFakeRates
                from ROOT import TauFakeRates as TFR
                fakerate_table = TauFakeRates.get_resource(
                        'FakeRateScaleFactor.txt')
                self.fakerate_tool = TFR.FakeRateScaler(fakerate_table)
                self.passes = self.passes_2011
            elif self.year == 12:
                from externaltools.bundle_2012 import TauFakeRates
                from ROOT import TauFakeRates as TFR
                self.fakerate_tool = TFR.FakeRateScaler(
                        TauFakeRates.RESOURCE_PATH)
                self.passes = self.passes_2012
            else:
                raise ValueError("No fakerates defined for year %d" % year)

        super(FakeRateScaleFactors, self).__init__(
                passthrough=passthrough, **kwargs)

    def passes_2011(self, event):

        if event.RunNumber >= 188902:
            trig = "EF_tau%dT_medium1"
        else:
            trig = "EF_tau%d_medium1"

        for tau in event.taus:
            # fakerate only applies to taus that don't match truth
            if not tau.matched:
                if tau.JetBDTSigTight:
                    wp = 'Tight'
                else:
                    wp = 'Medium'
                sf = self.fakerate_tool.getScaleFactor(
                        tau.pt, wp,
                        trig % tau.trigger_match_thresh)
                tau.fakerate_scale_factor = sf
                tau.fakerate_scale_factor_high = (sf +
                        self.fakerate_tool.getScaleFactorUncertainty(
                            tau.pt, wp,
                            trig % tau.trigger_match_thresh, True))
                tau.fakerate_scale_factor_low = (sf -
                        self.fakerate_tool.getScaleFactorUncertainty(
                            tau.pt, wp,
                            trig % tau.trigger_match_thresh, False))
        return True

    def passes_2012(self, event):

        trig = 'EF_tau%dTi_medium1'

        for tau in event.taus:
            # fakerate only applies to taus that don't match truth
            if not tau.matched:
                if tau.JetBDTSigTight:
                    wp = 'tight'
                else:
                    wp = 'medium'
                # last arg is lepton veto
                sf = self.fakerate_tool.getScaleFactor(
                        tau.pt, tau.numTrack, event.RunNumber,
                        'BDT', wp,
                        trig % tau.trigger_match_thresh, True)
                tau.fakerate_scale_factor = sf
                tau.fakerate_scale_factor_high = (sf +
                        self.fakerate_tool.getScaleFactorUncertainty(
                        tau.pt, tau.numTrack, event.RunNumber,
                        'BDT', wp,
                        trig % tau.trigger_match_thresh, True, True))
                tau.fakerate_scale_factor_low = (sf -
                        self.fakerate_tool.getScaleFactorUncertainty(
                        tau.pt, tau.numTrack, event.RunNumber,
                        'BDT', wp,
                        trig % tau.trigger_match_thresh, True, False))
        return True
