package org.batfish.representation.cisco;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;
import org.batfish.datamodel.Ip;

/** Cisco SR-TE policy before vendor-independent validation. */
@ParametersAreNonnullByDefault
public final class CiscoSrPolicy implements Serializable {
  private final String _name;
  private final List<CiscoSrCandidatePath> _candidates;
  @Nullable private Long _color;
  @Nullable private Ip _endpoint;

  public CiscoSrPolicy(String name) {
    _name = name;
    _candidates = new ArrayList<>();
  }

  public String getName() {
    return _name;
  }

  public List<CiscoSrCandidatePath> getCandidates() {
    return _candidates;
  }

  @Nullable
  public Long getColor() {
    return _color;
  }

  public void setColor(long color) {
    _color = color;
  }

  @Nullable
  public Ip getEndpoint() {
    return _endpoint;
  }

  public void setEndpoint(Ip endpoint) {
    _endpoint = endpoint;
  }
}
