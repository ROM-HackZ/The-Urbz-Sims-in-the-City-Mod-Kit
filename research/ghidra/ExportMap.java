// Seeds functions at known call targets, then exports a function map as JSON.
// args: <seed file: lines "ADDR arm|thumb"> <out json>
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.*;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.lang.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.math.BigInteger;
import java.util.*;
public class ExportMap extends GhidraScript {
  public void run() throws Exception {
    String[] a = getScriptArgs();
    Register tmode = currentProgram.getRegister("TMode");
    int created = 0;
    BufferedReader br = new BufferedReader(new FileReader(a[0]));
    String ln;
    while ((ln = br.readLine()) != null) {
      String[] p = ln.trim().split("\\s+");
      if (p.length < 2) continue;
      Address ad = toAddr(Long.parseLong(p[0], 16));
      if (getFunctionAt(ad) != null) continue;
      if (getInstructionAt(ad) == null) {
        if (getDataAt(ad) != null) continue;
        RegisterValue rv = new RegisterValue(tmode, p[1].equals("thumb") ? BigInteger.ONE : BigInteger.ZERO);
        DisassembleCommand dc = new DisassembleCommand(ad, null, true);
        dc.setInitialContext(rv);
        dc.applyTo(currentProgram, monitor);
      }
      if (getInstructionAt(ad) == null) continue;
      CreateFunctionCmd cf = new CreateFunctionCmd(ad);
      if (cf.applyTo(currentProgram, monitor)) created++;
    }
    println("created " + created);
    analyzeChanges(currentProgram);
    PrintWriter pw = new PrintWriter(new FileWriter(a[1]));
    pw.println("[");
    boolean first = true;
    ReferenceManager rm = currentProgram.getReferenceManager();
    for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
      Address e = f.getEntryPoint();
      Instruction ins = getInstructionAt(e);
      boolean thumb = false;
      if (ins != null) {
        RegisterValue v = ins.getRegisterValue(tmode);
        thumb = v != null && v.getUnsignedValue() != null && v.getUnsignedValue().intValue() == 1;
      }
      long mx = e.getOffset();
      for (AddressRange r : f.getBody()) mx = Math.max(mx, r.getMaxAddress().getOffset());
      StringBuilder calls = new StringBuilder();
      int nc = 0;
      for (Reference r : rm.getReferencesTo(e)) {
        if (!r.getReferenceType().isCall()) continue;
        if (nc++ > 0) calls.append(",");
        calls.append(r.getFromAddress().getOffset());
        if (nc >= 400) break;
      }
      pw.print((first ? "" : ",\n") + "{\"addr\":" + e.getOffset() + ",\"end\":" + (mx + 1) +
               ",\"thumb\":" + thumb + ",\"name\":\"" + f.getName() + "\",\"callers\":[" + calls + "]}");
      first = false;
    }
    pw.println("\n]");
    pw.close();
    println("exported " + currentProgram.getFunctionManager().getFunctionCount());
  }
}
